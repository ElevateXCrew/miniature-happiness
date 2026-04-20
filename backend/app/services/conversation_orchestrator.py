import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.core.logging import logger
from app.models.enums import Channel, InboundProvider, MessageDirection, SenderType
from app.models.message import Message
from app.repositories.client_repo import ClientRepository
from app.repositories.idempotency_repo import IdempotencyRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.agent_runtime import AgentRuntimeService
from app.services.media_service import MediaService
from app.services.notification_service import NotificationService
from app.services.twilio_gateway import TwilioGateway


@dataclass
class ProcessIncomingResult:
    duplicate: bool
    response_text: str | None
    session_id: uuid.UUID | None
    client_id: uuid.UUID | None
    outbound_message_sid: str | None
    replayed: bool = False


class ConversationOrchestrator:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.clients = ClientRepository(db)
        self.sessions = SessionRepository(db)
        self.messages = MessageRepository(db)
        self.idempotency = IdempotencyRepository(db)
        self.workers = WorkerRepository(db)
        self.runtime = AgentRuntimeService(db)
        self.media = MediaService(db)
        self.notifications = NotificationService(db)
        self.gateway = TwilioGateway()

    async def process_incoming(
        self,
        *,
        channel: Channel,
        phone_e164: str,
        inbound_text: str,
        message_sid: str,
        raw_payload: dict[str, Any] | None = None,
        media_items: list[dict[str, Any]] | None = None,
    ) -> ProcessIncomingResult:
        media_items = media_items or []
        normalized_phone = self.gateway.normalize_e164(phone_e164)
        existing_record = await self.idempotency.get_record(
            provider=InboundProvider.TWILIO,
            external_id=message_sid,
        )
        if existing_record is not None:
            metrics.incr("inbound_duplicates_total")
            replay_text = None
            replay_sid = None
            if existing_record.result_ref:
                try:
                    replay_msg = await self.messages.get_by_id(
                        uuid.UUID(existing_record.result_ref)
                    )
                except ValueError:
                    replay_msg = None
                if replay_msg is not None:
                    replay_text = replay_msg.body
                    replay_sid = replay_msg.twilio_message_sid
            return ProcessIncomingResult(
                duplicate=True,
                response_text=replay_text,
                session_id=None,
                client_id=None,
                outbound_message_sid=replay_sid,
                replayed=replay_text is not None,
            )

        already_processed = await self.idempotency.check_and_mark(
            provider=InboundProvider.TWILIO,
            external_id=message_sid,
        )
        if already_processed:
            metrics.incr("inbound_duplicates_total")
            return ProcessIncomingResult(
                duplicate=True,
                response_text=None,
                session_id=None,
                client_id=None,
                outbound_message_sid=None,
            )

        worker = await self.workers.get_active_worker()
        if worker is None:
            worker, _ = await self.workers.get_or_create_default(
                name=settings.default_worker_name,
                timezone=settings.default_worker_timezone,
            )

        client, _ = await self.clients.get_or_create(normalized_phone)
        session, _ = await self.sessions.get_or_create(
            client.id,
            worker.id,
            channel,
            update_last_inbound_at=False,
        )
        inbound_event_time = self._extract_inbound_event_time(raw_payload)
        if (
            inbound_event_time is not None
            and session.last_inbound_at is not None
            and inbound_event_time < self._as_utc(session.last_inbound_at)
        ):
            metrics.incr("inbound_out_of_order_total")
            await self.messages.save(
                Message(
                    session_id=session.id,
                    direction=MessageDirection.INBOUND,
                    channel=channel,
                    sender_type=SenderType.SYSTEM,
                    body="[out_of_order_inbound_ignored]",
                    raw_payload={
                        "message_sid": message_sid,
                        "event_time": inbound_event_time.isoformat(),
                    },
                )
            )
            return ProcessIncomingResult(
                duplicate=False,
                response_text=None,
                session_id=session.id,
                client_id=client.id,
                outbound_message_sid=None,
            )

        inbound_message = Message(
            session_id=session.id,
            direction=MessageDirection.INBOUND,
            channel=channel,
            sender_type=SenderType.CLIENT,
            body=inbound_text,
            twilio_message_sid=message_sid,
            raw_payload=raw_payload or {},
        )
        await self.messages.save(inbound_message)
        session.last_channel = channel
        session.last_inbound_at = inbound_event_time or datetime.now(UTC)
        await self.sessions.update(session)

        for media_item in media_items:
            await self.media.attach(
                client_id=client.id,
                session_id=session.id,
                source_url=media_item.get("source_url", ""),
                channel=channel,
                media_type=media_item.get("media_type"),
                twilio_media_sid=media_item.get("twilio_media_sid"),
            )

        effective_inbound_text = self._build_effective_inbound_text(
            inbound_text=inbound_text,
            media_items=media_items,
        )

        reply = await self.runtime.generate_reply(
            session_id=session.id,
            client_id=client.id,
            worker_id=worker.id,
            channel=channel,
            inbound_text=effective_inbound_text,
            attached_media_count=len(media_items),
        )

        send_result = await self.gateway.send_client_message(
            to_phone_e164=client.phone_e164,
            channel=channel.value,
            text=reply.text,
        )

        outbound = Message(
            session_id=session.id,
            direction=MessageDirection.OUTBOUND,
            channel=channel,
            sender_type=SenderType.AGENT,
            body=reply.text,
            twilio_message_sid=send_result.sid,
            raw_payload={
                "tool_traces": reply.tool_traces,
                "dispatch": {
                    "ok": send_result.ok,
                    "sid": send_result.sid,
                    "stub": send_result.stub,
                    "error": send_result.error,
                },
            },
        )
        await self.messages.save(outbound)
        await self.idempotency.set_result_ref(
            provider=InboundProvider.TWILIO,
            external_id=message_sid,
            result_ref=str(outbound.id),
        )

        if not send_result.ok:
            metrics.incr("twilio_outbound_send_failed_total")
            await self.notifications.queue_outbound_retry(
                client_id=client.id,
                channel=channel,
                text=reply.text,
                context={"source": "process_incoming", "session_id": str(session.id)},
                error=send_result.error,
                source="process_incoming",
            )
            logger.warning(
                "Twilio outbound send failed",
                client_id=str(client.id),
                session_id=str(session.id),
                error=send_result.error,
            )
        else:
            metrics.incr("twilio_outbound_send_ok_total")

        return ProcessIncomingResult(
            duplicate=False,
            response_text=reply.text,
            session_id=session.id,
            client_id=client.id,
            outbound_message_sid=send_result.sid,
        )

    async def send_message(
        self,
        *,
        client_id: uuid.UUID,
        channel: Channel,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            return {"ok": False, "error": "Client not found."}

        worker = await self.workers.get_active_worker()
        if worker is None:
            worker, _ = await self.workers.get_or_create_default(
                name=settings.default_worker_name,
                timezone=settings.default_worker_timezone,
            )

        session, _ = await self.sessions.get_or_create(client.id, worker.id, channel)
        send_result = await self.gateway.send_client_message(
            to_phone_e164=client.phone_e164,
            channel=channel.value,
            text=text,
        )

        outbound = Message(
            session_id=session.id,
            direction=MessageDirection.OUTBOUND,
            channel=channel,
            sender_type=SenderType.AGENT,
            body=text,
            twilio_message_sid=send_result.sid,
            raw_payload={
                "manual_send": True,
                "metadata": metadata or {},
                "dispatch": {
                    "ok": send_result.ok,
                    "sid": send_result.sid,
                    "stub": send_result.stub,
                    "error": send_result.error,
                },
            },
        )
        await self.messages.save(outbound)
        if send_result.ok:
            metrics.incr("twilio_outbound_send_ok_total")
        else:
            metrics.incr("twilio_outbound_send_failed_total")
            await self.notifications.queue_outbound_retry(
                client_id=client.id,
                channel=channel,
                text=text,
                context=metadata or {},
                error=send_result.error,
                source="send_message",
            )
        return {
            "ok": send_result.ok,
            "session_id": str(session.id),
            "message_id": str(outbound.id),
            "twilio_message_sid": send_result.sid,
            "stub": send_result.stub,
            "error": send_result.error,
        }

    def _extract_inbound_event_time(self, raw_payload: dict[str, Any] | None) -> datetime | None:
        if not raw_payload:
            return None
        candidates = [
            raw_payload.get("Timestamp"),
            raw_payload.get("MessageTimestamp"),
            raw_payload.get("SmsMessageSidTimestamp"),
        ]
        for value in candidates:
            if not value:
                continue
            text = str(value).strip()
            try:
                if text.endswith("Z"):
                    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                else:
                    parsed = datetime.fromisoformat(text)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return None

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _build_effective_inbound_text(
        self,
        *,
        inbound_text: str,
        media_items: list[dict[str, Any]],
    ) -> str:
        text = inbound_text.strip()
        if not media_items:
            return text

        media_count = len(media_items)
        media_note = (
            "Client sent 1 image attachment."
            if media_count == 1
            else f"Client sent {media_count} image attachments."
        )
        if text:
            return f"{text}\n\n[{media_note}]"
        return media_note
