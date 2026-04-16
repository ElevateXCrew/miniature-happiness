import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.twilio_gateway import TwilioGateway


@dataclass
class ProcessIncomingResult:
    duplicate: bool
    response_text: str | None
    session_id: uuid.UUID | None
    client_id: uuid.UUID | None
    outbound_message_sid: str | None


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
        already_processed = await self.idempotency.check_and_mark(
            provider=InboundProvider.TWILIO,
            external_id=message_sid,
        )
        if already_processed:
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
        session, _ = await self.sessions.get_or_create(client.id, worker.id, channel)

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

        for media_item in media_items:
            await self.media.attach(
                client_id=client.id,
                session_id=session.id,
                source_url=media_item.get("source_url", ""),
                channel=channel,
                media_type=media_item.get("media_type"),
                twilio_media_sid=media_item.get("twilio_media_sid"),
            )

        reply = await self.runtime.generate_reply(
            session_id=session.id,
            client_id=client.id,
            worker_id=worker.id,
            channel=channel,
            inbound_text=inbound_text,
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

        if not send_result.ok:
            logger.warning(
                "Twilio outbound send failed",
                client_id=str(client.id),
                session_id=str(session.id),
                error=send_result.error,
            )

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
        return {
            "ok": send_result.ok,
            "session_id": str(session.id),
            "message_id": str(outbound.id),
            "twilio_message_sid": send_result.sid,
            "stub": send_result.stub,
            "error": send_result.error,
        }
