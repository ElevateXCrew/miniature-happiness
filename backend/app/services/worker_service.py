"""
Worker command service: parses and executes worker intents.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Channel, MessageDirection, SenderType
from app.models.message import Message
from app.repositories.booking_repo import BookingRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.booking_service import BookingService
from app.services.event_stream import admin_event_stream
from app.services.twilio_gateway import TwilioGateway


@dataclass
class WorkerCommandResult:
    success: bool
    message: str
    executed_actions: list[dict[str, Any]]


@dataclass
class WorkerMessageResult:
    success: bool
    assistant_reply: str
    executed_actions: list[dict[str, Any]]


class WorkerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.worker_repo = WorkerRepository(db)
        self.booking_repo = BookingRepository(db)
        self.client_repo = ClientRepository(db)
        self.messages = MessageRepository(db)
        self.booking_service = BookingService(db)
        self.twilio = TwilioGateway()

    async def process_worker_message(
        self,
        worker_user_id: uuid.UUID,
        worker_id: uuid.UUID,
        message_text: str,
    ) -> WorkerMessageResult:
        worker = await self.worker_repo.get_by_id(worker_id)
        if worker is None or not worker.is_active:
            return WorkerMessageResult(
                success=False,
                assistant_reply="I couldn't find your worker profile right now.",
                executed_actions=[],
            )

        text = message_text.strip()
        lowered = text.lower()

        if self._is_next_booking_query(lowered):
            reply, actions = await self._handle_next_booking_query(worker_user_id, worker_id)
            return WorkerMessageResult(
                success=True,
                assistant_reply=reply,
                executed_actions=actions,
            )

        relay_text = self._extract_client_relay_text(text)
        if relay_text:
            relay_result = await self._handle_client_relay(
                worker_user_id=worker_user_id,
                worker_id=worker_id,
                relay_text=relay_text,
            )
            return relay_result

        if "free now" in lowered or "done early" in lowered or "finished" in lowered:
            command = await self._handle_free_now(worker_id)
            self._publish_worker_operation_event(
                worker_user_id=worker_user_id,
                operation="free_now",
                success=command.success,
                message=command.message,
                executed_actions=command.executed_actions,
            )
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=command.message,
                executed_actions=command.executed_actions,
            )
            return WorkerMessageResult(
                success=command.success,
                assistant_reply=command.message,
                executed_actions=command.executed_actions,
            )

        if lowered.startswith("block"):
            command = await self._handle_block_command(worker_id, lowered)
            self._publish_worker_operation_event(
                worker_user_id=worker_user_id,
                operation="availability_block",
                success=command.success,
                message=command.message,
                executed_actions=command.executed_actions,
            )
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=command.message,
                executed_actions=command.executed_actions,
            )
            return WorkerMessageResult(
                success=command.success,
                assistant_reply=command.message,
                executed_actions=command.executed_actions,
            )

        from app.services.agent_runtime import AgentRuntimeService

        runtime = AgentRuntimeService(self.db)
        reply_result = await runtime.generate_worker_chat_reply(
            worker_id=worker_id,
            inbound_text=text,
        )
        reply = reply_result.text
        self._publish_worker_chat_reply(
            worker_user_id=worker_user_id,
            reply=reply,
            executed_actions=[],
        )
        return WorkerMessageResult(success=True, assistant_reply=reply, executed_actions=[])

    async def process_command(self, worker_id: uuid.UUID, message_text: str) -> WorkerCommandResult:
        worker = await self.worker_repo.get_by_id(worker_id)
        if worker is None or not worker.is_active:
            return WorkerCommandResult(
                success=False,
                message="Worker not found or inactive.",
                executed_actions=[],
            )

        text = message_text.strip().lower()

        if "free now" in text or "done early" in text or "finished" in text:
            return await self._handle_free_now(worker_id)

        if text.startswith("block"):
            return await self._handle_block_command(worker_id, text)

        return WorkerCommandResult(
            success=False,
            message="Command not recognized.",
            executed_actions=[],
        )

    async def _handle_free_now(self, worker_id: uuid.UUID) -> WorkerCommandResult:
        from sqlalchemy import select

        from app.models.booking import Booking
        from app.models.enums import BookingStatus

        # Find the currently active CONFIRMED booking for this worker
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Booking).where(
                Booking.worker_id == worker_id,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.scheduled_start_at <= now,
            )
        )
        active = result.scalars().first()
        if not active:
            return WorkerCommandResult(
                success=False,
                message="I couldn't find an active booking to complete right now.",
                executed_actions=[],
            )

        _, errors = await self.booking_service.complete_early(
            booking_id=active.id,
            actor_ref=str(worker_id),
        )
        if errors:
            return WorkerCommandResult(
                success=False,
                message="; ".join(errors),
                executed_actions=[
                    {
                        "name": "booking.complete_early",
                        "ok": False,
                        "booking_id": str(active.id),
                        "error": "; ".join(errors),
                    }
                ],
            )
        admin_event_stream.publish(
            "worker.command.free_now",
            {
                "worker_id": str(worker_id),
                "booking_id": str(active.id),
                "result": "completed_early",
            },
        )
        return WorkerCommandResult(
            success=True,
            message="Done. I marked your active booking complete and freed the slot.",
            executed_actions=[
                {
                    "name": "booking.complete_early",
                    "ok": True,
                    "booking_id": str(active.id),
                    "status": "COMPLETED",
                }
            ],
        )

    async def _handle_block_command(self, worker_id: uuid.UUID, text: str) -> WorkerCommandResult:
        match = re.search(
            r"block\s+(\d{4}-\d{2}-\d{2}t\d{2}:\d{2})\s+(\d{4}-\d{2}-\d{2}t\d{2}:\d{2})", text
        )
        if not match:
            return WorkerCommandResult(
                success=False,
                message="Use: block YYYY-MM-DDTHH:MM YYYY-MM-DDTHH:MM",
                executed_actions=[],
            )
        start = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
        end = datetime.fromisoformat(match.group(2)).replace(tzinfo=UTC)
        if end <= start:
            return WorkerCommandResult(
                success=False,
                message="Block end must be after start.",
                executed_actions=[],
            )
        return await self.set_availability_override(
            worker_id=worker_id, from_at=start, to_at=end, mode="block"
        )

    async def set_availability_override(
        self,
        worker_id: uuid.UUID,
        from_at: datetime,
        to_at: datetime,
        mode: str,  # "block" or "unblock"
    ) -> WorkerCommandResult:
        # Availability overrides are modelled as audit events for now.
        # A dedicated availability_overrides table can be added in Phase 4.
        from app.models.enums import ActorType
        from app.repositories.audit_repo import AuditRepository

        audit = AuditRepository(self.db)
        await audit.log(
            entity_type="worker",
            entity_id=worker_id,
            event_type=f"availability_override:{mode}",
            actor_type=ActorType.WORKER,
            actor_ref=str(worker_id),
            metadata={"from_at": from_at.isoformat(), "to_at": to_at.isoformat(), "mode": mode},
        )
        admin_event_stream.publish(
            "worker.availability_override",
            {
                "worker_id": str(worker_id),
                "mode": mode,
                "from_at": from_at.isoformat(),
                "to_at": to_at.isoformat(),
            },
        )
        admin_event_stream.publish(
            "worker.operation.completed",
            {
                "worker_id": str(worker_id),
                "operation": f"availability.{mode}",
                "ok": True,
                "from_at": from_at.isoformat(),
                "to_at": to_at.isoformat(),
            },
        )
        return WorkerCommandResult(
            success=True,
            message=f"Availability {mode}ed from {from_at} to {to_at}.",
            executed_actions=[
                {
                    "name": f"availability.{mode}",
                    "ok": True,
                    "from_at": from_at.isoformat(),
                    "to_at": to_at.isoformat(),
                }
            ],
        )

    async def _handle_next_booking_query(
        self,
        worker_user_id: uuid.UUID,
        worker_id: uuid.UUID,
    ) -> tuple[str, list[dict[str, Any]]]:
        upcoming = await self.booking_repo.list_upcoming_confirmed(
            worker_id=worker_id,
            from_dt=datetime.now(UTC),
        )
        if not upcoming:
            actions = [{"name": "booking.lookup_next", "ok": True, "result": "none"}]
            reply = "You have no upcoming confirmed booking right now."
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=reply,
                executed_actions=actions,
            )
            return reply, actions

        timed_upcoming = [
            (b.scheduled_start_at, b)
            for b in upcoming
            if b.scheduled_start_at is not None
        ]
        if not timed_upcoming:
            actions = [{"name": "booking.lookup_next", "ok": True, "result": "none"}]
            reply = "I can see upcoming bookings, but none has a valid start time yet."
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=reply,
                executed_actions=actions,
            )
            return reply, actions

        next_booking = min(timed_upcoming, key=lambda item: item[0])[1]
        if next_booking.scheduled_start_at is None:
            actions = [{"name": "booking.lookup_next", "ok": True, "result": "none"}]
            reply = "I can see upcoming bookings, but none has a valid start time yet."
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=reply,
                executed_actions=actions,
            )
            return reply, actions
        scheduled_at = next_booking.scheduled_start_at.astimezone(UTC).isoformat()
        actions = [
            {
                "name": "booking.lookup_next",
                "ok": True,
                "booking_id": str(next_booking.id),
                "scheduled_start_at": scheduled_at,
                "duration_minutes": next_booking.duration_minutes,
                "booking_type": (
                    next_booking.booking_type.value if next_booking.booking_type else None
                ),
            }
        ]
        reply = f"Your next booking is at {scheduled_at}."
        self._publish_worker_chat_reply(
            worker_user_id=worker_user_id,
            reply=reply,
            executed_actions=actions,
        )
        return reply, actions

    async def _handle_client_relay(
        self,
        worker_user_id: uuid.UUID,
        worker_id: uuid.UUID,
        relay_text: str,
    ) -> WorkerMessageResult:
        from sqlalchemy import select

        from app.models.booking import Booking
        from app.models.enums import BookingStatus

        now = datetime.now(UTC)
        active_result = await self.db.execute(
            select(Booking).where(
                Booking.worker_id == worker_id,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.scheduled_start_at <= now,
            )
        )
        booking = active_result.scalars().first()
        if booking is None:
            upcoming = await self.booking_repo.list_upcoming_confirmed(
                worker_id=worker_id,
                from_dt=now,
            )
            timed_upcoming = [
                (b.scheduled_start_at, b)
                for b in upcoming
                if b.scheduled_start_at is not None
            ]
            booking = min(timed_upcoming, key=lambda item: item[0])[1] if timed_upcoming else None

        if booking is None:
            reply = "I couldn't find a current client to message."
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=reply,
                executed_actions=[],
            )
            return WorkerMessageResult(success=False, assistant_reply=reply, executed_actions=[])

        client = await self.client_repo.get_by_id(booking.client_id)
        if client is None:
            reply = "I couldn't find that client record right now."
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=reply,
                executed_actions=[],
            )
            return WorkerMessageResult(success=False, assistant_reply=reply, executed_actions=[])

        session = await self.messages.list_for_session(booking.session_id)
        channel = Channel.WHATSAPP
        if session:
            channel = session[-1].channel

        from app.services.agent_runtime import AgentRuntimeService

        runtime = AgentRuntimeService(self.db)
        relay_reply = await runtime.generate_worker_relay_reply(
            session_id=booking.session_id,
            client_id=client.id,
            worker_id=worker_id,
            channel=channel,
            worker_instruction=relay_text,
        )
        outbound_text = relay_reply.text

        send_result = await self.twilio.send_client_message(
            to_phone_e164=client.phone_e164,
            channel=channel.value,
            text=outbound_text,
        )
        await self.messages.save(
            Message(
                session_id=booking.session_id,
                direction=MessageDirection.OUTBOUND,
                channel=channel,
                sender_type=SenderType.AGENT,
                body=outbound_text,
                twilio_message_sid=send_result.sid,
                raw_payload={
                    "worker_relay": True,
                    "worker_id": str(worker_id),
                    "worker_instruction": relay_text,
                    "tool_traces": relay_reply.tool_traces,
                    "dispatch": {
                        "ok": send_result.ok,
                        "sid": send_result.sid,
                        "stub": send_result.stub,
                        "error": send_result.error,
                    },
                },
            )
        )

        if not send_result.ok:
            reply = "I couldn't deliver that message yet. Please try again in a moment."
            actions = [
                {
                    "name": "client.message.send",
                    "ok": False,
                    "booking_id": str(booking.id),
                    "error": send_result.error,
                }
            ]
            self._publish_worker_operation_event(
                worker_user_id=worker_user_id,
                operation="client_message_relay",
                success=False,
                message=reply,
                executed_actions=actions,
            )
            self._publish_worker_chat_reply(
                worker_user_id=worker_user_id,
                reply=reply,
                executed_actions=actions,
            )
            return WorkerMessageResult(
                success=False,
                assistant_reply=reply,
                executed_actions=actions,
            )

        actions = [
            {
                "name": "client.message.send",
                "ok": True,
                "booking_id": str(booking.id),
                "channel": channel.value,
                "sid": send_result.sid,
            }
        ]
        reply = "Done. I sent that to the client."
        self._publish_worker_operation_event(
            worker_user_id=worker_user_id,
            operation="client_message_relay",
            success=True,
            message=reply,
            executed_actions=actions,
        )
        self._publish_worker_chat_reply(
            worker_user_id=worker_user_id,
            reply=reply,
            executed_actions=actions,
        )
        return WorkerMessageResult(success=True, assistant_reply=reply, executed_actions=actions)

    def _is_next_booking_query(self, text: str) -> bool:
        return (
            "next booking" in text
            or "my next booking" in text
            or "next booking time" in text
            or ("when" in text and "booking" in text and "next" in text)
        )

    def _extract_client_relay_text(self, text: str) -> str | None:
        lowered = text.lower()
        prefixes = [
            "tell him to",
            "tell client to",
            "message client",
            "send to client",
            "tell the client",
        ]
        for prefix in prefixes:
            idx = lowered.find(prefix)
            if idx >= 0:
                relay = text[idx + len(prefix) :].strip()
                if relay:
                    return relay
        if lowered.startswith("relay "):
            relay = text[6:].strip()
            if relay:
                return relay
        return None

    def _publish_worker_chat_reply(
        self,
        *,
        worker_user_id: uuid.UUID,
        reply: str,
        executed_actions: list[dict[str, Any]],
    ) -> None:
        admin_event_stream.publish(
            "worker.chat_reply",
            {
                "worker_user_id": str(worker_user_id),
                "reply": reply,
                "executed_actions": executed_actions,
            },
        )

    def _publish_worker_operation_event(
        self,
        *,
        worker_user_id: uuid.UUID,
        operation: str,
        success: bool,
        message: str,
        executed_actions: list[dict[str, Any]],
    ) -> None:
        admin_event_stream.publish(
            "worker.operation.completed",
            {
                "worker_user_id": str(worker_user_id),
                "operation": operation,
                "ok": success,
                "message": message,
                "executed_actions": executed_actions,
            },
        )
