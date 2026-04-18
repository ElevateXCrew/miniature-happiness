import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.core.logging import logger
from app.models.booking import Booking
from app.models.enums import (
    ActorType,
    AwaitingReviewFrom,
    BookingStatus,
    Channel,
    ConversationState,
    MessageDirection,
)
from app.repositories.audit_repo import AuditRepository
from app.repositories.booking_repo import BookingRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.tools.tool_runner import ToolRunner

_BOOKING_INTENT_TERMS = {
    "book",
    "booking",
    "see you",
    "appointment",
    "meet",
    "available",
    "availability",
    "slot",
}
_YES_TERMS = {"yes", "y", "yeah", "yep", "confirm", "go ahead", "ok", "okay"}


@dataclass
class AgentReply:
    text: str
    tool_traces: list[dict[str, Any]]


class AgentRuntimeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.messages = MessageRepository(db)
        self.bookings = BookingRepository(db)
        self.audit = AuditRepository(db)
        self.sessions = SessionRepository(db)
        self.booking_service = BookingService(db)
        self.availability = AvailabilityService(db)
        self.tool_runner = ToolRunner(db)
        self._openai_client: AsyncOpenAI | None = None

    async def generate_reply(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
        inbound_text: str,
        attached_media_count: int,
    ) -> AgentReply:
        if channel == Channel.SMS and attached_media_count > 0:
            return AgentReply(
                text="Can you send that receipt on WhatsApp on this same number, babe?",
                tool_traces=[],
            )

        if settings.openai_api_key.strip():
            try:
                return await self._generate_llm_reply(
                    session_id=session_id,
                    client_id=client_id,
                    worker_id=worker_id,
                    channel=channel,
                    inbound_text=inbound_text,
                )
            except Exception as exc:
                logger.warning("LLM orchestration failed, falling back", error=str(exc))

        return await self._generate_fallback_reply(
            session_id=session_id,
            client_id=client_id,
            worker_id=worker_id,
            channel=channel,
            inbound_text=inbound_text,
        )

    async def _generate_llm_reply(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
        inbound_text: str,
    ) -> AgentReply:
        system_prompt = self._load_channel_prompt(channel)
        history = await self.messages.list_for_session(session_id)

        confirm_reply = await self._handle_llm_confirmation_reply(
            session_id=session_id,
            inbound_text=inbound_text,
            history=history,
        )
        if confirm_reply is not None:
            return confirm_reply

        chat_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for msg in history[-12:]:
            role = "user" if msg.direction == MessageDirection.INBOUND else "assistant"
            chat_messages.append({"role": role, "content": msg.body or ""})
        chat_messages.append({"role": "user", "content": inbound_text})

        tools = self._tool_specs()
        tool_traces: list[dict[str, Any]] = []

        client = self._get_openai_client()

        for _ in range(5):
            completion = await cast(Any, client.chat.completions).create(
                model=settings.openai_model,
                temperature=0.2,
                messages=chat_messages,
                tools=tools,
                tool_choice="auto",
            )
            msg = completion.choices[0].message

            if msg.tool_calls:
                chat_messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )

                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = await self._execute_tool(name, args, client_id, worker_id, channel)
                    tool_traces.append({"name": name, "arguments": args, "result": result})

                    if (
                        name == "check_availability"
                        and not result.get("ok", False)
                        and isinstance(result.get("error"), str)
                        and str(result.get("error", "")).startswith("Invalid datetime format")
                    ):
                        return AgentReply(
                            text="Send the date and time like 2026-04-18T20:30, babe.",
                            tool_traces=tool_traces,
                        )

                    chat_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        }
                    )
                continue

            content = (msg.content or "").strip()
            if content:
                return AgentReply(text=self._ensure_short_style(content), tool_traces=tool_traces)

        return AgentReply(
            text="I can help with that babe. What date and time did you want?",
            tool_traces=tool_traces,
        )

    async def _handle_llm_confirmation_reply(
        self,
        *,
        session_id: uuid.UUID,
        inbound_text: str,
        history: list[Any],
    ) -> AgentReply | None:
        lowered = inbound_text.strip().lower()
        if not any(token in lowered for token in _YES_TERMS):
            return None

        if not self._was_recent_confirmation_prompt(history):
            return None

        session = await self.sessions.get_by_id(session_id)
        if session is None or session.active_booking_id is None:
            return AgentReply(
                text="I lost that booking draft. Send your date/time and I'll re-check.",
                tool_traces=[],
            )

        booking = await self.bookings.get_by_id(session.active_booking_id)
        if booking is None:
            return AgentReply(
                text="I lost that booking draft. Send your date/time and I'll re-check.",
                tool_traces=[],
            )

        if booking.status != BookingStatus.DRAFT:
            return None

        booking_after_submit, errors = await self.booking_service.submit_for_review(
            booking_id=booking.id,
            reviewer=AwaitingReviewFrom.ADMIN,
            actor_type=ActorType.AGENT,
        )
        if errors:
            return AgentReply(text=errors[0], tool_traces=[])

        if booking_after_submit and booking_after_submit.status == BookingStatus.PENDING_REVIEW:
            return AgentReply(
                text="Perfect babe, I've sent it for review. Please wait a moment.",
                tool_traces=[],
            )
        return None

    def _was_recent_confirmation_prompt(self, history: list[Any]) -> bool:
        for msg in reversed(history):
            if msg.direction != MessageDirection.OUTBOUND:
                continue
            body = (msg.body or "").lower()
            if not body:
                return False
            return ("reply yes" in body) or ("to confirm" in body) or ("just to confirm" in body)
        return False

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
    ) -> dict[str, Any]:
        method = getattr(self.tool_runner, name, None)
        if method is None:
            metrics.incr("tool_calls_failed_total")
            return {"ok": False, "error": f"Unknown tool: {name}"}

        patch_args = dict(args)
        if name == "get_or_create_client_by_phone" and "phone_e164" not in patch_args:
            return {"ok": False, "error": "phone_e164 is required"}
        if name == "get_or_create_active_session":
            patch_args.setdefault("client_id", str(client_id))
            patch_args.setdefault("worker_id", str(worker_id))
            patch_args.setdefault("channel", channel.value)
        if name == "check_availability":
            # Always enforce server-trusted worker identity and ignore model-provided values.
            patch_args["worker_id"] = str(worker_id)

        try:
            result = await method(**patch_args)
        except Exception as exc:
            metrics.incr("tool_calls_failed_total")
            await self.audit.log(
                entity_type="client",
                entity_id=client_id,
                event_type="tool_execution_failed",
                actor_type=ActorType.AGENT,
                metadata={"tool": name, "arguments": patch_args, "error": str(exc)},
            )
            return {"ok": False, "error": str(exc)}

        if name == "check_availability" and result.get("ok", False):
            await self._ensure_draft_booking_after_availability(
                client_id=client_id,
                worker_id=worker_id,
                tool_args=patch_args,
            )

        if result.get("ok"):
            metrics.incr("tool_calls_ok_total")
            event = "tool_execution_ok"
        else:
            metrics.incr("tool_calls_failed_total")
            event = "tool_execution_failed"
        await self.audit.log(
            entity_type="client",
            entity_id=client_id,
            event_type=event,
            actor_type=ActorType.AGENT,
            metadata={"tool": name, "arguments": patch_args, "result": result},
        )
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
        return {"ok": False, "error": "Tool returned invalid response type."}

    async def _ensure_draft_booking_after_availability(
        self,
        *,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        tool_args: dict[str, Any],
    ) -> None:
        session = await self.sessions.get_active_for_client_worker(client_id, worker_id)
        if session is None:
            return

        if session.active_booking_id is not None:
            active_booking = await self.bookings.get_by_id(session.active_booking_id)
            if active_booking is not None:
                return

        existing_draft = await self.bookings.get_active_draft_for_session(session.id)
        if existing_draft is not None:
            session.active_booking_id = existing_draft.id
            await self.sessions.update(session)
            return

        start_at = self._parse_tool_datetime(tool_args.get("start_at"))
        duration = self._parse_tool_duration(tool_args.get("duration_minutes"))
        if start_at is None or duration is None:
            return

        booking = Booking(
            client_id=client_id,
            worker_id=worker_id,
            session_id=session.id,
            status=BookingStatus.DRAFT,
            scheduled_start_at=start_at,
            duration_minutes=duration,
            scheduled_end_at=start_at + timedelta(minutes=duration),
        )
        await self.bookings.save(booking)

        session.active_booking_id = booking.id
        if session.state == ConversationState.IDLE:
            session.state = ConversationState.COLLECTING
        await self.sessions.update(session)

    def _parse_tool_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None
        normalized = raw.replace(" ", "T", 1) if " " in raw and "T" not in raw else raw
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _parse_tool_duration(self, value: Any) -> int | None:
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            return None
        if minutes <= 0:
            return None
        return minutes

    async def _generate_fallback_reply(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
        inbound_text: str,
    ) -> AgentReply:
        session = await self.sessions.get_by_id(session_id)
        if session is None:
            return AgentReply(text="Hey babe, message me again in a sec.", tool_traces=[])

        text = inbound_text.strip()
        lowered = text.lower()

        if session.state == ConversationState.AWAITING_CLIENT_CONFIRMATION:
            if any(token in lowered for token in _YES_TERMS):
                if not session.active_booking_id:
                    return AgentReply(
                        text="I lost that booking draft. Send your date/time and I'll re-check.",
                        tool_traces=[],
                    )
                booking, errors = await self.booking_service.submit_for_review(
                    booking_id=session.active_booking_id,
                    reviewer=AwaitingReviewFrom.ADMIN,
                    actor_type=ActorType.AGENT,
                )
                if errors:
                    return AgentReply(text=errors[0], tool_traces=[])
                if booking and booking.status == BookingStatus.PENDING_REVIEW:
                    return AgentReply(
                        text="Perfect babe, I've sent it for review. Please wait a moment.",
                        tool_traces=[],
                    )

        booking = await self._get_or_create_draft_if_intent(
            session_id=session_id,
            client_id=client_id,
            worker_id=worker_id,
            session_state=session.state,
            text=lowered,
        )

        if booking is None:
            return AgentReply(text="Hey babe 😘 how are you?", tool_traces=[])

        if session.state != ConversationState.COLLECTING:
            session.state = ConversationState.COLLECTING
            await self.sessions.update(session)

        next_field = self.booking_service.get_next_required_field(booking)
        if next_field is not None:
            update_error = await self._attempt_field_capture(booking.id, next_field, text)
            if update_error is None:
                booking = await self.bookings.get_by_id(booking.id) or booking
                next_field = self.booking_service.get_next_required_field(booking)
            else:
                return AgentReply(text=update_error, tool_traces=[])

        if next_field is not None:
            return AgentReply(text=self._question_for_field(next_field), tool_traces=[])

        if booking.scheduled_start_at is None or booking.duration_minutes is None:
            return AgentReply(
                text="What date/time and duration should I check babe?",
                tool_traces=[],
            )

        availability = await self.availability.check(
            worker_id=worker_id,
            proposed_start=booking.scheduled_start_at,
            duration_minutes=booking.duration_minutes,
            exclude_booking_id=booking.id,
        )
        if not availability.available:
            alternative = (
                availability.suggested_start.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
                if availability.suggested_start
                else "another nearby time"
            )
            return AgentReply(
                text=f"That slot isn't free babe. I can do {alternative} instead.",
                tool_traces=[],
            )

        scheduled_label = booking.scheduled_start_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        summary = (
            f"Just to confirm: {scheduled_label}, {booking.duration_minutes} mins, "
            f"age {booking.client_age}, ethnicity {booking.client_ethnicity}. "
            "Reply yes to confirm."
        )
        session.state = ConversationState.AWAITING_CLIENT_CONFIRMATION
        await self.sessions.update(session)
        return AgentReply(text=summary, tool_traces=[])

    async def _get_or_create_draft_if_intent(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        session_state: ConversationState,
        text: str,
    ) -> Booking | None:
        existing = await self.bookings.get_active_draft_for_session(session_id)
        if existing is not None:
            return existing

        if session_state == ConversationState.COLLECTING:
            return None

        if not any(term in text for term in _BOOKING_INTENT_TERMS):
            return None

        booking = Booking(
            client_id=client_id,
            worker_id=worker_id,
            session_id=session_id,
            status=BookingStatus.DRAFT,
        )
        await self.bookings.save(booking)
        session = await self.sessions.get_by_id(session_id)
        if session:
            session.active_booking_id = booking.id
            session.state = ConversationState.COLLECTING
            await self.sessions.update(session)
        return booking

    async def _attempt_field_capture(
        self,
        booking_id: uuid.UUID,
        field_name: str,
        text: str,
    ) -> str | None:
        if field_name == "scheduled_start_at":
            dt = self._extract_datetime(text)
            if dt is None:
                return "What date and time should I pencil in? (e.g. 2026-05-01 19:30)"
            _, errors = await self.booking_service.update_field(booking_id, field_name, dt)
            return errors[0] if errors else None

        if field_name == "client_age":
            age = self._extract_age(text)
            if age is None:
                return "Before we continue, confirm your age please (18+)."
            _, errors = await self.booking_service.update_field(booking_id, field_name, age)
            return errors[0] if errors else None

        if field_name == "client_ethnicity":
            value = text.strip()
            if not value:
                return "Tell me your ethnicity please babe."
            _, errors = await self.booking_service.update_field(booking_id, field_name, value)
            return errors[0] if errors else None

        if field_name == "duration_minutes":
            duration = self._extract_duration_minutes(text)
            if duration is None:
                return "How long would you like? (e.g. 60 mins)"
            _, errors = await self.booking_service.update_field(booking_id, field_name, duration)
            return errors[0] if errors else None

        return None

    def _question_for_field(self, field_name: str) -> str:
        if field_name == "scheduled_start_at":
            return "What date and time do you want babe?"
        if field_name == "client_age":
            return "Confirm your age for me please (18+)."
        if field_name == "client_ethnicity":
            return "What ethnicity are you babe?"
        if field_name == "duration_minutes":
            return "How long do you want to book for?"
        return "Can you share that detail for me?"

    def _extract_datetime(self, text: str) -> datetime | None:
        text = text.strip()
        iso_candidate = text.replace("/", "-")
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H.%M"):
            try:
                parsed = datetime.strptime(iso_candidate, fmt)
                return parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    def _extract_age(self, text: str) -> int | None:
        match = re.search(r"\b(\d{2})\b", text)
        if not match:
            return None
        return int(match.group(1))

    def _extract_duration_minutes(self, text: str) -> int | None:
        lower = text.lower()
        hour_match = re.search(r"\b(\d{1,2})\s*(hour|hr|hrs|hours)\b", lower)
        if hour_match:
            return int(hour_match.group(1)) * 60

        min_match = re.search(r"\b(\d{2,3})\s*(min|mins|minute|minutes)?\b", lower)
        if min_match:
            return int(min_match.group(1))
        return None

    def _load_channel_prompt(self, channel: Channel) -> str:
        root = Path(__file__).resolve().parents[3]
        prompts_dir = root / "prompts"
        file_name = "whatsapp.txt" if channel == Channel.WHATSAPP else "sms.txt"
        prompt_path = prompts_dir / file_name
        context_path = prompts_dir / "alysha_context.md"

        parts: list[str] = []

        # Inject the Alysha identity/rate context first so the channel prompt
        # can reference "your profile" without re-stating everything.
        if context_path.exists():
            parts.append(context_path.read_text(encoding="utf-8").strip())

        if prompt_path.exists():
            parts.append(prompt_path.read_text(encoding="utf-8").strip())
        else:
            parts.append("You are Alysha. Keep messages brief, warm, and human.")

        return "\n\n---\n\n".join(parts)

    def _get_openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def _ensure_short_style(self, text: str) -> str:
        # Collapse blank lines but allow multi-line responses (bank details,
        # confirmation summaries) through.  The system prompt itself instructs
        # the LLM to keep replies short; we trust it for legitimate multi-line
        # content rather than blindly truncating.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "Sure babe."
        return "\n".join(lines)

    def _tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_availability",
                    "description": (
                        "Check slot availability with 15-minute buffer. "
                        "IMPORTANT: start_at MUST be ISO 8601 with date AND time, "
                        "e.g. '2026-04-19T20:00'. Never pass date-only or natural language."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "worker_id": {"type": "string"},
                            "start_at": {"type": "string"},
                            "duration_minutes": {"type": "integer"},
                        },
                        "required": ["worker_id", "start_at", "duration_minutes"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_required_next_field",
                    "description": "Get the next required booking field in strict order.",
                    "parameters": {
                        "type": "object",
                        "properties": {"booking_id": {"type": "string"}},
                        "required": ["booking_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_booking_field",
                    "description": "Update exactly one booking field with validation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {"type": "string"},
                            "field_name": {"type": "string"},
                            "field_value": {},
                        },
                        "required": ["booking_id", "field_name", "field_value"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_booking_fields",
                    "description": "Validate draft booking and report missing fields.",
                    "parameters": {
                        "type": "object",
                        "properties": {"booking_id": {"type": "string"}},
                        "required": ["booking_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_booking_for_review",
                    "description": "Move draft booking to pending review.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {"type": "string"},
                            "reviewer": {"type": "string"},
                        },
                        "required": ["booking_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "route_media_request_to_whatsapp",
                    "description": "Ask the SMS user to send media via WhatsApp.",
                    "parameters": {
                        "type": "object",
                        "properties": {"client_id": {"type": "string"}},
                        "required": ["client_id"],
                    },
                },
            },
        ]
