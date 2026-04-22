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
    BookingType,
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
    "interested",
    "interest",
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


class ClientRuntimeService:
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

    def _admin_action_fallback_reply(self, inbound_text: str) -> AgentReply | None:
        """
        Intercept [ADMIN ACTION: ...] directives when the LLM is unavailable.
        Returns a static Alysha-voiced reply so the fallback path never garbles
        a booking decision into a date-collection prompt.
        """
        stripped = inbound_text.strip()
        if not stripped.startswith("[ADMIN ACTION:"):
            return None
        lowered = stripped.lower()
        if "confirmed" in lowered:
            return AgentReply(
                text="You're confirmed babe! So excited to see you, it's going to be amazing xx",
                tool_traces=[],
            )
        if "rejected" in lowered:
            return AgentReply(
                text="Sorry babe, that slot isn't available now. Want to try a different time? 💕",
                tool_traces=[],
            )
        if "cancelled" in lowered:
            return AgentReply(
                text="Booking cancelled babe. Message me whenever you want to rebook 😊",
                tool_traces=[],
            )
        return AgentReply(text="Got it babe, I'll update you shortly 😊", tool_traces=[])

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

        # Admin action directives are handled with a static reply when LLM is
        # unavailable; when the LLM IS available it processes them naturally.
        if not settings.openai_api_key.strip():
            admin_reply = self._admin_action_fallback_reply(inbound_text)
            if admin_reply is not None:
                return admin_reply

        if settings.openai_api_key.strip():
            try:
                reply = await self._generate_llm_reply(
                    session_id=session_id,
                    client_id=client_id,
                    worker_id=worker_id,
                    channel=channel,
                    inbound_text=inbound_text,
                )
                if channel == Channel.WHATSAPP and attached_media_count > 0:
                    return AgentReply(
                        text=await self._apply_media_ack_policy(
                            session_id=session_id,
                            channel=channel,
                            text=reply.text,
                        ),
                        tool_traces=reply.tool_traces,
                    )
                return reply
            except Exception as exc:
                logger.warning("LLM orchestration failed, falling back", error=str(exc))

        fallback_reply = await self._generate_fallback_reply(
            session_id=session_id,
            client_id=client_id,
            worker_id=worker_id,
            channel=channel,
            inbound_text=inbound_text,
        )
        if channel == Channel.WHATSAPP and attached_media_count > 0:
            return AgentReply(
                text=await self._apply_media_ack_policy(
                    session_id=session_id,
                    channel=channel,
                    text=fallback_reply.text,
                ),
                tool_traces=fallback_reply.tool_traces,
            )
        return fallback_reply

    async def _apply_media_ack_policy(
        self,
        *,
        session_id: uuid.UUID,
        channel: Channel,
        text: str,
    ) -> str:
        acked = self._ensure_media_ack_in_reply(text)
        lowered = acked.lower()

        if channel == Channel.WHATSAPP and "whatsapp" in lowered and "send" in lowered:
            return "I have received your photo/screenshot babe 😊"

        review_markers = ("just reviewing", "i'll confirm soon", "ill confirm soon")
        if any(marker in lowered for marker in review_markers):
            has_review_context = await self._has_pending_review_context(session_id)
            if not has_review_context:
                return (
                    "I have received your photo/screenshot babe 😊 "
                    "Share your date and time and I'll sort the booking for you."
                )

        return acked

    async def _has_pending_review_context(self, session_id: uuid.UUID) -> bool:
        session = await self.sessions.get_by_id(session_id)
        if session is None:
            return False

        review_statuses = {BookingStatus.PENDING_REVIEW, BookingStatus.CONFIRMED}

        if session.active_booking_id is not None:
            active = await self.bookings.get_by_id(session.active_booking_id)
            if active is not None and active.status in review_statuses:
                return True

        latest = await self.bookings.get_latest_for_session(session_id)
        return latest is not None and latest.status in review_statuses

    async def generate_admin_decision_reply(
        self,
        *,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
        decision_instruction: str,
    ) -> AgentReply:
        """Generate an admin decision follow-up in Alysha's voice using chat context."""
        if not settings.openai_api_key.strip():
            admin_reply = self._admin_action_fallback_reply(decision_instruction)
            if admin_reply is not None:
                return admin_reply
            return AgentReply(text="Got it babe, I'll update you shortly 😊", tool_traces=[])

        try:
            session = await self.sessions.get_by_id(session_id)
            if session is None:
                admin_reply = self._admin_action_fallback_reply(decision_instruction)
                if admin_reply is not None:
                    return admin_reply
                return AgentReply(text="Got it babe, I'll update you shortly 😊", tool_traces=[])

            booking_context = await self._build_booking_context_block(session)
            system_prompt = self._load_channel_prompt(channel, extra_context=booking_context)
            history = await self.messages.list_for_session(session_id)

            chat_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            for msg in history[-16:]:
                role = "user" if msg.direction == MessageDirection.INBOUND else "assistant"
                chat_messages.append({"role": role, "content": msg.body or ""})

            chat_messages.append(
                {
                    "role": "system",
                    "content": (
                        "[SYSTEM ADMIN DECISION CONTEXT] "
                        f"{decision_instruction} "
                        "Keep continuity with the recent conversation. "
                        "Output only the client-facing message in 1-2 lines."
                    ),
                }
            )
            chat_messages.append(
                {
                    "role": "user",
                    "content": "Send the booking decision update now.",
                }
            )

            client = self._get_openai_client()
            completion = await cast(Any, client.chat.completions).create(
                model=settings.openai_model,
                temperature=0.2,
                messages=chat_messages,
            )
            content = (completion.choices[0].message.content or "").strip()
            if content:
                return AgentReply(text=self._ensure_short_style(content), tool_traces=[])
        except Exception as exc:
            logger.warning("Admin decision LLM generation failed, using fallback", error=str(exc))

        admin_reply = self._admin_action_fallback_reply(decision_instruction)
        if admin_reply is not None:
            return admin_reply
        return AgentReply(text="Got it babe, I'll update you shortly 😊", tool_traces=[])

    def _ensure_media_ack_in_reply(self, text: str) -> str:
        lowered = (text or "").lower()
        ack_markers = (
            "received",
            "got your",
            "got it",
            "photo",
            "screenshot",
            "image",
            "receipt",
        )
        if any(marker in lowered for marker in ack_markers):
            return text
        return (
            f"I have received your photo/screenshot babe 😊\n{text}"
            if text
            else "I have received your photo/screenshot babe 😊"
        )

    async def _generate_llm_reply(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
        inbound_text: str,
    ) -> AgentReply:
        session = await self.sessions.get_by_id(session_id)
        if session is None:
            return AgentReply(text="Hey babe 😘", tool_traces=[])

        await self._sync_draft_from_inbound(session_id=session_id, inbound_text=inbound_text)
        await self._pre_capture_required_field_from_inbound(
            session_id=session_id,
            inbound_text=inbound_text,
        )

        status_guard = await self._handle_active_booking_status_guard(session)
        if status_guard is not None:
            return status_guard

        booking_context = await self._build_booking_context_block(session)
        system_prompt = self._load_channel_prompt(channel, extra_context=booking_context)
        history = await self.messages.list_for_session(session_id)

        confirm_reply = await self._handle_llm_confirmation_reply(
            session_id=session_id,
            inbound_text=inbound_text,
            history=history,
        )
        if confirm_reply is not None:
            return confirm_reply

        if not settings.openai_api_key.strip():
            return await self._generate_fallback_reply(
                session_id=session_id,
                client_id=client_id,
                worker_id=worker_id,
                channel=channel,
                inbound_text=inbound_text,
            )

        chat_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        history_window = history if len(history) <= 120 else history[-120:]
        for msg in history_window:
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

                field_saved_this_turn = False
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = await self._execute_tool(
                        name,
                        args,
                        client_id,
                        worker_id,
                        channel,
                        inbound_text=inbound_text,
                    )
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

                    if name == "update_booking_field" and result.get("ok"):
                        field_saved_this_turn = True

                if field_saved_this_turn:
                    directive = (
                        "[SYSTEM — internal only, never quote this to the client] "
                        "A booking field was just saved. Continue naturally in Alysha's voice, "
                        "using booking records so you do not re-ask saved fields."
                    )
                    chat_messages.append({"role": "system", "content": directive})
                continue

            content = (msg.content or "").strip()
            if content:
                await self._maybe_set_awaiting_confirmation_state(session_id=session_id)
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

        session = await self.sessions.get_by_id(session_id)
        if session is None:
            return None

        if session.state != ConversationState.AWAITING_CLIENT_CONFIRMATION:
            if not self._was_recent_confirmation_prompt(history):
                return None

        if session.active_booking_id is None:
            terminal_reply = await self._reply_for_latest_session_booking(session.id)
            if terminal_reply is not None:
                return terminal_reply
            return AgentReply(
                text="I lost that booking draft. Send your date/time and I'll re-check.",
                tool_traces=[],
            )

        booking = await self.bookings.get_by_id(session.active_booking_id)
        if booking is None:
            terminal_reply = await self._reply_for_latest_session_booking(session.id)
            if terminal_reply is not None:
                return terminal_reply
            return AgentReply(
                text="I lost that booking draft. Send your date/time and I'll re-check.",
                tool_traces=[],
            )

        if booking.status != BookingStatus.DRAFT:
            return None

        # Guard: if required fields are still missing the "yes" is an answer to a
        # collection question (e.g. "Yes my age is 21"), not a final confirmation.
        # Let the LLM handle field extraction instead of trying to submit early.
        next_field = self.booking_service.get_next_required_field(booking)
        if next_field is not None:
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
                text=(
                    "Perfect babe, I'm just finalizing everything. "
                    "I'll message you in a moment 😊"
                ),
                tool_traces=[],
            )
        return None

    async def _reply_for_latest_session_booking(self, session_id: uuid.UUID) -> AgentReply | None:
        latest = await self.bookings.get_latest_for_session(session_id)
        if latest is None:
            return None

        if latest.status == BookingStatus.CONFIRMED:
            return AgentReply(text="You're confirmed babe. See you soon xx", tool_traces=[])
        if latest.status == BookingStatus.PENDING_REVIEW:
            return AgentReply(
                text="Perfect babe, it's with admin now. I'll update you soon.",
                tool_traces=[],
            )
        if latest.status == BookingStatus.REJECTED:
            return AgentReply(
                text="Sorry babe, that slot isn't available now. Want to try a different time? 💕",
                tool_traces=[],
            )
        if latest.status == BookingStatus.CANCELLED:
            return AgentReply(
                text="Booking cancelled babe. Message me whenever you want to rebook 😊",
                tool_traces=[],
            )
        if latest.status == BookingStatus.COMPLETED:
            return AgentReply(
                text="That booking's all done babe. Want to arrange another? 😊",
                tool_traces=[],
            )
        return None

    async def _maybe_set_awaiting_confirmation_state(self, *, session_id: uuid.UUID) -> None:
        session = await self.sessions.get_by_id(session_id)
        if session is None or session.active_booking_id is None:
            return

        if session.state in {
            ConversationState.AWAITING_CLIENT_CONFIRMATION,
            ConversationState.WAITING_REVIEW,
        }:
            return

        booking = await self.bookings.get_by_id(session.active_booking_id)
        if booking is None or booking.status != BookingStatus.DRAFT:
            return

        next_field = self.booking_service.get_next_required_field(booking)
        if next_field is not None:
            return

        if booking.scheduled_start_at is None or booking.duration_minutes is None:
            return

        session.state = ConversationState.AWAITING_CLIENT_CONFIRMATION
        await self.sessions.update(session)

    def _was_recent_confirmation_prompt(self, history: list[Any]) -> bool:
        for msg in reversed(history):
            if msg.direction != MessageDirection.OUTBOUND:
                continue
            body = (msg.body or "").lower()
            if not body:
                return False
            return (
                "reply yes" in body
                or "to confirm" in body
                or "just to confirm" in body
                or "shall i go ahead" in body
                or "go ahead?" in body
                or "shall we go ahead" in body
            )
        return False

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
        inbound_text: str | None = None,
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
            session = await self.sessions.get_active_for_client_worker(client_id, worker_id)
            has_active_draft = bool(
                session is not None and session.active_booking_id is not None
            )
            if not has_active_draft and not self._has_booking_intent(inbound_text or ""):
                return {
                    "ok": False,
                    "error": (
                        "Check availability only after the client clearly shows booking intent. "
                        "Keep it conversational first."
                    ),
                }

        # Guard: if the LLM passed a non-UUID booking_id (e.g. "DRAFT"), resolve
        # the real active draft for this client/worker and substitute it in.
        _BOOKING_ID_TOOLS = {
            "get_required_next_field",
            "advisory_check_booking_field_update",
            "update_booking_field",
            "validate_booking_fields",
            "submit_booking_for_review",
        }
        if name in _BOOKING_ID_TOOLS and "booking_id" in patch_args:
            raw_bid = str(patch_args["booking_id"]).strip()
            try:
                uuid.UUID(raw_bid)
            except ValueError:
                # Not a real UUID — look up the active draft from the session.
                session = await self.sessions.get_active_for_client_worker(client_id, worker_id)
                resolved_id: uuid.UUID | None = None
                if session is not None and session.active_booking_id is not None:
                    resolved_id = session.active_booking_id
                else:
                    # Fall back to querying the draft directly.
                    if session is not None:
                        draft = await self.bookings.get_active_draft_for_session(session.id)
                        if draft is not None:
                            resolved_id = draft.id
                if resolved_id is None:
                    metrics.incr("tool_calls_failed_total")
                    return {
                        "ok": False,
                        "error": (
                            f"booking_id '{raw_bid}' is not valid and no active draft found. "
                            "Call check_availability first to create a draft."
                        ),
                    }
                patch_args["booking_id"] = str(resolved_id)

        if name == "advisory_check_booking_field_update":
            guard_error = await self._guard_update_field_from_inbound(
                patch_args=patch_args,
                inbound_text=inbound_text or "",
            )
            result: dict[str, Any] = {
                "ok": True,
                "allowed": guard_error is None,
                "reason": (
                    "Field update is allowed for the current inbound message."
                    if guard_error is None
                    else guard_error
                ),
            }
            metrics.incr("tool_calls_ok_total")
            await self.audit.log(
                entity_type="client",
                entity_id=client_id,
                event_type="tool_execution_ok",
                actor_type=ActorType.AGENT,
                metadata={"tool": name, "arguments": patch_args, "result": result},
            )
            return result

        if name == "update_booking_field":
            guard_error = await self._guard_update_field_from_inbound(
                patch_args=patch_args,
                inbound_text=inbound_text or "",
            )
            if guard_error is not None:
                metrics.incr("tool_calls_failed_total")
                return {"ok": False, "error": guard_error}

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
                inbound_text=inbound_text or "",
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
            return result
        return {"ok": False, "error": "Tool returned invalid response type."}

    async def _guard_update_field_from_inbound(
        self,
        *,
        patch_args: dict[str, Any],
        inbound_text: str,
    ) -> str | None:
        """
        Block model hallucinations by allowing booking field updates only when:
        1) the field is the next required collection field, and
        2) the client's current inbound text supports that value.
        """
        booking_id_raw = str(patch_args.get("booking_id", "")).strip()
        field_name = str(patch_args.get("field_name", "")).strip()
        field_value = patch_args.get("field_value")
        if not booking_id_raw or not field_name:
            return "booking_id and field_name are required."

        try:
            booking_id = uuid.UUID(booking_id_raw)
        except ValueError:
            return "Invalid booking_id."

        booking = await self.bookings.get_by_id(booking_id)
        if booking is None:
            return "Booking not found."

        strict_fields = {
            "scheduled_start_at",
            "booking_type",
            "duration_minutes",
            "outcall_address",
            "client_age",
            "client_ethnicity",
            "client_size_inches",
            "alone_policy_confirmed",
        }
        if field_name in strict_fields:
            expected_next = self.booking_service.get_next_required_field(booking)
            if expected_next is not None and field_name != expected_next:
                return (
                    "Do not save this field yet. "
                    f"Collect '{expected_next}' next in order."
                )

        text = (inbound_text or "").strip().lower()
        value_text = str(field_value).strip().lower()
        if not text:
            return "No inbound text provided for field validation."

        if field_name == "booking_type":
            extracted = self._extract_booking_type(inbound_text)
            if extracted is None or extracted.value != value_text:
                return "Booking type must come from the client's current message."

        if field_name == "duration_minutes":
            extracted_minutes = self._extract_duration_minutes(inbound_text)
            if field_value is None:
                return "Invalid duration value."
            try:
                requested_minutes = int(field_value)
            except (TypeError, ValueError):
                return "Invalid duration value."
            if extracted_minutes is None or extracted_minutes != requested_minutes:
                return "Duration must match what the client just said."

        if field_name == "client_age":
            age_cues = ("age", "old", "year", "years", "i am", "i'm")
            extracted_age = self._extract_age(inbound_text)
            if field_value is None:
                return "Invalid age value."
            try:
                requested_age = int(field_value)
            except (TypeError, ValueError):
                return "Invalid age value."
            if extracted_age is None or extracted_age != requested_age:
                return "Age must match the client's current message."
            if not any(cue in text for cue in age_cues):
                return "Do not infer age without an explicit age statement."

        if field_name == "client_ethnicity":
            if value_text and value_text not in text:
                return "Ethnicity must come from the client's current message."

        if field_name == "outcall_address":
            if value_text and value_text not in text:
                return "Outcall address must come from the client's current message."

        if field_name == "client_size_inches":
            extracted_size = self._extract_size_inches(inbound_text)
            if field_value is None:
                return "Invalid size value."
            try:
                requested_size = int(field_value)
            except (TypeError, ValueError):
                return "Invalid size value."
            if extracted_size is None or extracted_size != requested_size:
                return "Size must match the client's current message."

        if field_name == "alone_policy_confirmed":
            extracted_policy = self._extract_alone_policy(inbound_text)
            if isinstance(field_value, str):
                normalized = field_value.strip().lower()
                if normalized in {"yes", "y", "true", "1"}:
                    requested_policy = True
                elif normalized in {"no", "n", "false", "0"}:
                    requested_policy = False
                else:
                    return "Invalid alone policy value."
            else:
                requested_policy = bool(field_value)
            if extracted_policy is None or extracted_policy != requested_policy:
                return "One-on-one confirmation must come from the client's current message."

        return None

    async def _ensure_draft_booking_after_availability(
        self,
        *,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        tool_args: dict[str, Any],
        inbound_text: str,
    ) -> None:
        session = await self.sessions.get_active_for_client_worker(client_id, worker_id)
        if session is None:
            return

        start_at = self._parse_tool_datetime(tool_args.get("start_at"))
        tool_duration = self._parse_tool_duration(tool_args.get("duration_minutes"))
        extracted_duration = self._extract_duration_minutes(inbound_text)
        persisted_duration = (
            tool_duration if extracted_duration is not None and tool_duration is not None else None
        )

        if session.active_booking_id is not None:
            active_booking = await self.bookings.get_by_id(session.active_booking_id)
            if active_booking is not None:
                updated = False
                if active_booking.scheduled_start_at is None and start_at is not None:
                    active_booking.scheduled_start_at = start_at
                    updated = True
                if active_booking.duration_minutes is None and persisted_duration is not None:
                    active_booking.duration_minutes = persisted_duration
                    if active_booking.scheduled_start_at is not None:
                        active_booking.scheduled_end_at = (
                            active_booking.scheduled_start_at
                            + timedelta(minutes=persisted_duration)
                        )
                    updated = True
                if updated:
                    await self.bookings.save(active_booking)
                return

        existing_draft = await self.bookings.get_active_draft_for_session(session.id)
        if existing_draft is not None:
            session.active_booking_id = existing_draft.id
            await self.sessions.update(session)
            updated = False
            if existing_draft.scheduled_start_at is None and start_at is not None:
                existing_draft.scheduled_start_at = start_at
                updated = True
            if existing_draft.duration_minutes is None and persisted_duration is not None:
                existing_draft.duration_minutes = persisted_duration
                if existing_draft.scheduled_start_at is not None:
                    existing_draft.scheduled_end_at = (
                        existing_draft.scheduled_start_at
                        + timedelta(minutes=persisted_duration)
                    )
                updated = True
            if updated:
                await self.bookings.save(existing_draft)
            return

        if start_at is None:
            return

        booking = Booking(
            client_id=client_id,
            worker_id=worker_id,
            session_id=session.id,
            status=BookingStatus.DRAFT,
            scheduled_start_at=start_at,
            duration_minutes=persisted_duration,
            scheduled_end_at=(
                start_at + timedelta(minutes=persisted_duration)
                if persisted_duration is not None
                else None
            ),
        )
        await self.bookings.save(booking)

        session.active_booking_id = booking.id
        if session.state == ConversationState.IDLE:
            session.state = ConversationState.COLLECTING
        await self.sessions.update(session)

    async def _sync_draft_from_inbound(self, *, session_id: uuid.UUID, inbound_text: str) -> None:
        session = await self.sessions.get_by_id(session_id)
        if session is None or session.active_booking_id is None:
            return

        booking = await self.bookings.get_by_id(session.active_booking_id)
        if booking is None or booking.status != BookingStatus.DRAFT:
            return

        booking_type = self._extract_booking_type(inbound_text)
        if booking_type is not None and booking.booking_type is None:
            await self.booking_service.update_field(
                booking_id=booking.id,
                field_name="booking_type",
                field_value=booking_type.value,
                actor_type=ActorType.AGENT,
            )

    async def _pre_capture_required_field_from_inbound(
        self,
        *,
        session_id: uuid.UUID,
        inbound_text: str,
    ) -> None:
        """
        Capture the next required field directly from inbound text before the
        LLM call so the model does not re-ask a question that the client just
        answered in the same turn.
        """
        session = await self.sessions.get_by_id(session_id)
        if session is None or session.active_booking_id is None:
            return

        booking = await self.bookings.get_by_id(session.active_booking_id)
        if booking is None or booking.status != BookingStatus.DRAFT:
            return

        next_field = self.booking_service.get_next_required_field(booking)
        if next_field is None:
            return

        # Best-effort bulk capture: extract as many fields as possible from
        # a single inbound message while still respecting required order.
        text = inbound_text.strip()
        if not text:
            return

        for _ in range(8):
            latest_booking = await self.bookings.get_by_id(booking.id)
            if latest_booking is None:
                return

            current_field = self.booking_service.get_next_required_field(latest_booking)
            if current_field is None:
                return

            update_error = await self._attempt_field_capture(
                booking_id=booking.id,
                field_name=current_field,
                text=text,
            )
            if update_error is not None:
                return

    async def _handle_active_booking_status_guard(
        self,
        session: Any,
    ) -> AgentReply | None:
        if session.active_booking_id is None:
            return None

        booking = await self.bookings.get_by_id(session.active_booking_id)
        if booking is None:
            return None

        if booking.status == BookingStatus.PENDING_REVIEW:
            return AgentReply(
                text="Perfect babe, it's with admin now. I'll update you soon.",
                tool_traces=[],
            )

        if booking.status == BookingStatus.CONFIRMED:
            return AgentReply(
                text="You're confirmed babe. See you soon xx",
                tool_traces=[],
            )

        return None

    def _is_smalltalk_or_greeting(self, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return True

        greetings = {
            "hi",
            "hy",
            "hey",
            "hello",
            "hiya",
            "yo",
            "good morning",
            "good afternoon",
            "good evening",
            "how are you",
        }
        compact = re.sub(r"[^a-z\s]", "", lowered).strip()
        if compact in greetings:
            return True
        return any(compact.startswith(g + " ") for g in greetings)

    def _worker_chat_fallback_reply(self, text: str) -> str:
        if self._is_smalltalk_or_greeting(text):
            return "Hi babe 😘"
        lowered = text.strip().lower()
        if lowered.endswith("?"):
            return "Sure babe 😊"
        return "Okay babe 😊"

    def _extract_booking_type(self, text: str) -> BookingType | None:
        lowered = text.strip().lower()
        if not lowered:
            return None

        incall_terms = ("incall", "come to me", "your place")
        outcall_terms = ("outcall", "come to you", "my place", "hotel")

        if any(term in lowered for term in incall_terms):
            return BookingType.INCALL
        if any(term in lowered for term in outcall_terms):
            return BookingType.OUTCALL
        return None

    def _has_booking_intent(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        if self._is_smalltalk_or_greeting(lowered):
            return False
        return any(term in lowered for term in _BOOKING_INTENT_TERMS)

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
        # Admin action directives must never be processed as client input.
        admin_reply = self._admin_action_fallback_reply(inbound_text)
        if admin_reply is not None:
            return admin_reply

        session = await self.sessions.get_by_id(session_id)
        if session is None:
            return AgentReply(text="Hey babe, message me again in a sec.", tool_traces=[])

        text = inbound_text.strip()
        lowered = text.lower()

        if session.state == ConversationState.AWAITING_CLIENT_CONFIRMATION:
            if any(token in lowered for token in _YES_TERMS):
                if not session.active_booking_id:
                    terminal_reply = await self._reply_for_latest_session_booking(session.id)
                    if terminal_reply is not None:
                        return terminal_reply
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
                        text=(
                            "Perfect babe, your booking is in progress "
                            "and I will message you shortly 😊"
                        ),
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
            if self._is_smalltalk_or_greeting(text):
                return AgentReply(text="Hi babe 😘", tool_traces=[])
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
        booking_type = (booking.booking_type.value.upper() if booking.booking_type else "BOOKING")
        summary_parts = [
            (
                f"Just to confirm babe - {booking_type} on {scheduled_label} for "
                f"{booking.duration_minutes} mins."
            )
        ]
        if booking.booking_type == BookingType.INCALL:
            summary_parts.append("Address: City Centre, Birmingham B16 8FP.")
        elif booking.booking_type == BookingType.OUTCALL:
            summary_parts.append("For outcall it's rate + Uber and a 50 GBP advance.")
            if booking.outcall_address:
                summary_parts.append(f"Your address: {booking.outcall_address}.")
        summary = " ".join(summary_parts)
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
            value = self._extract_ethnicity(text)
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

        if field_name == "booking_type":
            booking_type = self._extract_booking_type(text)
            if booking_type is None:
                return "Would you prefer incall or outcall, babe?"
            _, errors = await self.booking_service.update_field(
                booking_id,
                field_name,
                booking_type.value,
            )
            return errors[0] if errors else None

        if field_name == "outcall_address":
            value = self._extract_outcall_address(text)
            if len(value) < 4:
                return "Share your area or full address for outcall babe."
            _, errors = await self.booking_service.update_field(booking_id, field_name, value)
            return errors[0] if errors else None

        if field_name == "client_size_inches":
            size_inches = self._extract_size_inches(text)
            if size_inches is None:
                return "One more thing babe - what size are you?"
            _, errors = await self.booking_service.update_field(booking_id, field_name, size_inches)
            return errors[0] if errors else None

        if field_name == "alone_policy_confirmed":
            alone_value = self._extract_alone_policy(text)
            if alone_value is None:
                return "It'll just be you, right babe? I only do one-on-one."
            _, errors = await self.booking_service.update_field(
                booking_id,
                field_name,
                alone_value,
            )
            return errors[0] if errors else None

        return None

    def _question_for_field(self, field_name: str) -> str:
        if field_name == "scheduled_start_at":
            return "What date and time do you want babe?"
        if field_name == "booking_type":
            return "Would you prefer incall or outcall, babe?"
        if field_name == "outcall_address":
            return "Share your area or address for outcall babe."
        if field_name == "client_name":
            return "What's your name babe?"
        if field_name == "client_age":
            return "Confirm your age for me please (18+)."
        if field_name == "client_ethnicity":
            return "What ethnicity are you babe?"
        if field_name == "duration_minutes":
            return "How long do you want to book for?"
        if field_name == "client_size_inches":
            return "One more thing babe - what size are you?"
        if field_name == "alone_policy_confirmed":
            return "It'll just be you, right babe? I only do one-on-one."
        return "Can you share that detail for me?"

    def _extract_ethnicity(self, text: str) -> str | None:
        lowered = text.lower()
        labeled = re.search(r"\bethnicity\s*(?:is|:)?\s*([a-z][a-z\s\-/]{1,40})", lowered)
        if labeled:
            value = labeled.group(1).strip(" .,!?")
            return value if value else None

        known = (
            "asian",
            "british asian",
            "white",
            "black",
            "mixed",
            "arab",
            "indian",
            "pakistani",
            "bangladeshi",
            "chinese",
        )
        for token in known:
            if token in lowered:
                return token
        return None

    def _extract_outcall_address(self, text: str) -> str:
        lowered = text.lower()
        outcall_labeled = re.search(
            r"\boutcall\s*[:\-]\s*(.+?)(?=(?:\b(?:duration|age|ethnicity|size|alone|name)\b\s*[:\-])|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if outcall_labeled:
            value = outcall_labeled.group(1).strip(" .,!?\n\t")
            if len(value) >= 4:
                return value

        labeled = re.search(
            r"\b(?:address|area|location)\s*(?:is|:)?\s*(.+)$",
            text,
            re.IGNORECASE,
        )
        if labeled:
            return labeled.group(1).strip()

        location_tokens = (
            " road",
            " street",
            " st ",
            " avenue",
            " ave ",
            "birmingham",
            "manchester",
            "london",
            "postcode",
            "flat",
            "apartment",
            "hotel",
        )
        if any(token in lowered for token in location_tokens):
            return text.strip()

        # When the flow is explicitly waiting for outcall address, accept a
        # reasonably detailed free-text location line even without keywords.
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) >= 10 and len(compact.split()) >= 3:
            return compact
        return ""

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
        lowered = text.lower().strip()
        patterns = (
            r"\bage\s*(?:is|:)?\s*(\d{2})\b",
            r"\b(?:i am|i'm|im)\s*(\d{2})\b(?!\s*[:.])",
            r"\b(\d{2})\s*(?:years?\s*old|years?|yrs?)\b",
            r"\b(\d{2})\s*yo\b",
        )

        for pattern in patterns:
            match = re.search(pattern, lowered)
            if not match:
                continue
            try:
                age = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 18 <= age <= 99:
                return age
        return None

    def _extract_duration_minutes(self, text: str) -> int | None:
        lower = text.lower()
        hour_match = re.search(r"\b(\d{1,2})\s*(hour|hr|hrs|hours)\b", lower)
        if hour_match:
            return int(hour_match.group(1)) * 60

        min_match = re.search(r"\b(\d{2,3})\s*(min|mins|minute|minutes)?\b", lower)
        if min_match:
            return int(min_match.group(1))
        return None

    def _extract_size_inches(self, text: str) -> int | None:
        labeled = re.search(
            r"\bsize\s*(?:is|:)?\s*(\d{1,2})\b",
            text,
            re.IGNORECASE,
        )
        if labeled:
            return int(labeled.group(1))

        match = re.search(r"\b(\d{1,2})\b", text)
        if not match:
            return None
        return int(match.group(1))

    def _extract_alone_policy(self, text: str) -> bool | None:
        lowered = text.strip().lower()
        negative_tokens = ("not alone", "friend", "friends", "group")
        positive_phrases = ("that's fine", "thats fine", "just me", "only me")

        if any(token in lowered for token in negative_tokens):
            return False

        if re.search(r"\b(?:no|we|two|2)\b", lowered):
            return False

        if any(phrase in lowered for phrase in positive_phrases):
            return True

        if re.search(r"\b(?:yes|y|ok|okay|fine|sure|alone)\b", lowered):
            return True
        return None

    def _load_channel_prompt(self, channel: Channel, extra_context: str | None = None) -> str:
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

        # Inject live booking state so the LLM never re-asks for fields already collected.
        if extra_context:
            parts.append(extra_context)

        return "\n\n---\n\n".join(parts)

    async def _build_booking_context_block(self, session: Any) -> str | None:
        """
        Build the [Your booking records for this client] block that is injected
        into every system prompt.  This is the SINGLE source of truth the LLM
        uses to know which fields are already collected so it never re-asks them.
        """
        now_uk = datetime.now(UTC).strftime("%A, %d %B %Y — %H:%M")
        lines: list[str] = [
            f"[Current date and time in UK]: {now_uk}",
        ]

        booking: Any = None
        if session.active_booking_id is not None:
            booking = await self.bookings.get_by_id(session.active_booking_id)

        if booking is None or booking.status not in (BookingStatus.DRAFT,):
            # No active draft — give the LLM just the current time.
            lines.append("[Your booking records for this client]: No active booking draft.")
            return "\n".join(lines)

        has_receipt = await self.booking_service.media.has_receipt_for_booking(booking.id)

        # Format the draft booking fields for the LLM.
        def fmt_dt(value: Any) -> str:
            if value is None:
                return "NOT YET PROVIDED"
            try:
                return str(value.astimezone(UTC).strftime("%A %d %B %Y at %H:%M"))
            except Exception:
                return str(value)

        booking_type_label = (
            booking.booking_type.value.capitalize() if booking.booking_type else "NOT YET PROVIDED"
        )

        dur_line = (
            f"  Duration: {booking.duration_minutes} mins"
            if booking.duration_minutes
            else "  Duration: NOT YET PROVIDED"
        )
        name_line = (
            f"  Client name: {booking.client_name}"
            if booking.client_name
            else "  Client name: not provided (optional)"
        )
        age_line = (
            f"  Client age: {booking.client_age}"
            if booking.client_age is not None
            else "  Client age: NOT YET PROVIDED"
        )
        eth_line = (
            f"  Client ethnicity: {booking.client_ethnicity}"
            if booking.client_ethnicity
            else "  Client ethnicity: NOT YET PROVIDED"
        )
        size_line = (
            f"  Client size: {booking.client_size_inches} inches"
            if booking.client_size_inches is not None
            else "  Client size: NOT YET PROVIDED"
        )
        alone_policy_line = (
            "  Alone policy: Confirmed — just them"
            if booking.alone_policy_confirmed is True
            else (
                "  Alone policy: Declined — not alone"
                if booking.alone_policy_confirmed is False
                else "  Alone policy: NOT YET ASKED"
            )
        )
        records = [
            f"  booking_id (use this exact value for tool calls): {booking.id}",
            f"  Date & time: {fmt_dt(booking.scheduled_start_at)}",
            f"  Booking type: {booking_type_label}",
            dur_line,
            name_line,
            age_line,
            eth_line,
            size_line,
            alone_policy_line,
            "  Payment receipt: RECEIVED"
            if has_receipt
            else "  Payment receipt: NOT RECEIVED",
        ]

        lines.append("[Your booking records for this client]:")
        lines.extend(records)
        collection_order = (
            "DATE -> BOOKING TYPE -> DURATION -> OUTCALL ADDRESS (if outcall) -> "
            "AGE -> ETHNICITY -> SIZE -> ALONE POLICY -> FINAL CONFIRMATION"
        )
        lines.append(
            "\nSTAY IN CHARACTER: You are Alysha (real person, not a bot). "
            "Never mention checking, validation, collection, or system terms."
            "\n✓ NATURAL FLOW: Keep the conversation natural and concise, and collect missing "
            "details without robotic phrasing."
            "\n✓ FIELD ORDER: Collect missing fields in this order: " + collection_order + "."
            "\n✓ SKIP FILLED FIELDS: Never ask for a field that already has a value above."
            "\n✓ INTEREST GATE: If no active draft exists, only begin booking collection after "
            "clear booking intent from the client."
            "\n✓ FINAL CONFIRMATION: After all required fields are present, send a warm summary "
            "and wait for YES."
            "\n✓ INCALL ADDRESS TIMING: Share incall address only in final confirmation summary."
        )
        return "\n".join(lines)

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
                    "name": "advisory_check_booking_field_update",
                    "description": (
                        "Advisory-only guard check for booking field updates. "
                        "Returns whether the proposed update is allowed by the same "
                        "runtime guard used for update_booking_field; does not save data."
                    ),
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

