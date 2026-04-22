"""
Booking service: enforces state machine transitions and field validation.
All state changes go through here — never set booking.status directly outside this service.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.models.enums import (
    ActorType,
    AwaitingReviewFrom,
    BookingStatus,
    ConversationState,
    MessageDirection,
    SenderType,
)
from app.models.message import Message
from app.repositories.audit_repo import AuditRepository
from app.repositories.booking_repo import BookingRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.availability_service import AvailabilityService
from app.services.event_stream import admin_event_stream
from app.services.media_service import MediaService
from app.services.notification_service import NotificationService

# Required field collection order (matches STATE_MACHINE.md and prompt booking steps)
# Step order: 1-date, 2-type, 3-duration, 4-address(outcall), 5-name(optional),
#            6-age, 7-ethnicity, 7b-size, 8-alone_policy
REQUIRED_FIELD_ORDER = [
    "scheduled_start_at",        # Step 1 — Date & time (CRITICAL: must be first)
    # Step 2 — Booking type (CRITICAL: must come before duration/address)
    "booking_type",
    "duration_minutes",          # Step 3 — Duration (after type so we can quote correct rate)
    "client_age",                # Step 6 — Age (MANDATORY, guard: must be 18+)
    "client_ethnicity",          # Step 7 — Ethnicity (MANDATORY)
    "client_size_inches",        # Step 7b — Size screening (MANDATORY, guard: <= 6 inches)
    "alone_policy_confirmed",    # Step 8 — Alone policy (MANDATORY)
]

OPTIONAL_FIELDS = [
    "client_name",               # Step 5 — Name (OPTIONAL: accepted if skipped)
    "outcall_address",           # Step 4 — Address (only for outcall bookings)
]


@dataclass
class FieldValidationResult:
    complete: bool
    next_required_field: str | None
    errors: list[str]


class BookingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = BookingRepository(db)
        self.session_repo = SessionRepository(db)
        self.client_repo = ClientRepository(db)
        self.audit = AuditRepository(db)
        self.availability = AvailabilityService(db)
        self.notifications = NotificationService(db)
        self.media = MediaService(db)

    # ------------------------------------------------------------------
    # Field inspection
    # ------------------------------------------------------------------

    def get_next_required_field(self, booking: Any) -> str | None:
        """
        Returns the name of the next unfilled required field, or None if all done.
        Special logic: outcall_address is required only for OUTCALL bookings,
        and must be collected after duration but before client details.
        """
        # For OUTCALL bookings, check if we need the address first
        # (after booking_type and duration but before client age/ethnicity)
        if (
            booking.booking_type is not None
            and booking.booking_type.value == "outcall"
            and booking.duration_minutes is not None
            and not (booking.outcall_address or "").strip()
        ):
            return "outcall_address"

        for field in REQUIRED_FIELD_ORDER:
            value = getattr(booking, field, None)
            if value is None:
                return field
        return None

    def validate_fields(self, booking: Any) -> FieldValidationResult:
        errors: list[str] = []
        next_field = self.get_next_required_field(booking)

        # Age guard
        if booking.client_age is not None and booking.client_age < 18:
            errors.append("Client must be 18 or older.")

        # Ethnicity guard
        if booking.client_ethnicity is not None and booking.client_ethnicity.strip() == "":
            errors.append("Ethnicity cannot be blank.")

        # Duration guard
        if booking.duration_minutes is not None and booking.duration_minutes <= 0:
            errors.append("Duration must be a positive number of minutes.")

        # Size screening guard
        if booking.client_size_inches is not None and booking.client_size_inches > 6:
            errors.append("Client size exceeds allowed limit.")

        # Alone policy guard
        if booking.alone_policy_confirmed is False:
            errors.append("Booking must be one-on-one only.")

        complete = next_field is None and len(errors) == 0
        return FieldValidationResult(
            complete=complete,
            next_required_field=next_field,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Field update (atomic, validated)
    # ------------------------------------------------------------------

    async def update_field(
        self,
        booking_id: uuid.UUID,
        field_name: str,
        field_value: Any,
        actor_type: ActorType = ActorType.AGENT,
        actor_ref: str | None = None,
    ) -> tuple[Any, list[str]]:
        """
        Updates a single booking field with validation.
        Returns (updated_booking, errors).
        """
        booking = await self.repo.get_by_id(booking_id)
        if not booking:
            return None, [f"Booking {booking_id} not found."]

        errors: list[str] = []

        if field_name == "client_age":
            age = int(field_value)
            if age < 18:
                errors.append("Client must be 18 or older.")
                return booking, errors
            booking.client_age = age

        elif field_name == "client_ethnicity":
            if not str(field_value).strip():
                errors.append("Ethnicity cannot be blank.")
                return booking, errors
            booking.client_ethnicity = str(field_value).strip()

        elif field_name == "client_size_inches":
            try:
                size_inches = int(field_value)
            except (TypeError, ValueError):
                errors.append("Size must be a number in inches.")
                return booking, errors
            if size_inches <= 0:
                errors.append("Size must be greater than 0.")
                return booking, errors
            booking.client_size_inches = size_inches

        elif field_name == "alone_policy_confirmed":
            if isinstance(field_value, str):
                normalized = field_value.strip().lower()
                if normalized in {"yes", "y", "true", "1"}:
                    booking.alone_policy_confirmed = True
                elif normalized in {"no", "n", "false", "0"}:
                    booking.alone_policy_confirmed = False
                else:
                    errors.append("Please confirm if it will be one-on-one.")
                    return booking, errors
            else:
                booking.alone_policy_confirmed = bool(field_value)

        elif field_name == "scheduled_start_at":
            if isinstance(field_value, str):
                field_value = datetime.fromisoformat(field_value)
            booking.scheduled_start_at = field_value
            # Recompute end if duration known
            if booking.duration_minutes:
                booking.scheduled_end_at = field_value + timedelta(minutes=booking.duration_minutes)

        elif field_name == "duration_minutes":
            mins = int(field_value)
            if mins <= 0:
                errors.append("Duration must be positive.")
                return booking, errors
            booking.duration_minutes = mins
            if booking.scheduled_start_at:
                booking.scheduled_end_at = booking.scheduled_start_at + timedelta(minutes=mins)

        elif field_name == "client_name":
            booking.client_name = str(field_value).strip() or None

        elif field_name == "booking_type":
            from app.models.enums import BookingType

            booking.booking_type = BookingType(field_value)

        elif field_name == "outcall_address":
            booking.outcall_address = str(field_value).strip()

        elif field_name == "price_total_gbp":
            try:
                booking.price_total_gbp = Decimal(str(field_value))
            except (InvalidOperation, ValueError):
                errors.append("Price total must be a valid GBP amount.")
                return booking, errors

        elif field_name == "advance_required_gbp":
            try:
                amount = Decimal(str(field_value))
            except (InvalidOperation, ValueError):
                errors.append("Advance required must be a valid GBP amount.")
                return booking, errors
            booking.advance_required_gbp = amount

        elif field_name == "advance_received":
            booking.advance_received = bool(field_value)

        elif field_name == "incall_address_sent_at":
            if isinstance(field_value, str):
                field_value = datetime.fromisoformat(field_value)
            booking.incall_address_sent_at = field_value

        else:
            errors.append(f"Unknown field: {field_name}")
            return booking, errors

        await self.repo.save(booking)
        await self.audit.log(
            entity_type="booking",
            entity_id=booking_id,
            event_type=f"field_updated:{field_name}",
            actor_type=actor_type,
            actor_ref=actor_ref,
            metadata={"field": field_name, "value": str(field_value)},
        )
        admin_event_stream.publish(
            "booking.field_updated",
            {
                "booking_id": str(booking.id),
                "field": field_name,
                "value": str(field_value),
                "actor_type": actor_type.value,
            },
        )
        return booking, errors

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    async def submit_for_review(
        self,
        booking_id: uuid.UUID,
        reviewer: AwaitingReviewFrom = AwaitingReviewFrom.ADMIN,
        actor_type: ActorType = ActorType.AGENT,
        actor_ref: str | None = None,
    ) -> tuple[Any, list[str]]:
        """
        Transitions booking: DRAFT -> PENDING_REVIEW.
        Re-checks availability before moving.
        """
        booking = await self.repo.get_by_id(booking_id)
        if not booking:
            return None, ["Booking not found."]

        if booking.status != BookingStatus.DRAFT:
            return booking, [f"Cannot submit booking in status {booking.status}."]

        validation = self.validate_fields(booking)
        if not validation.complete:
            if validation.errors:
                return booking, validation.errors
            # Map internal field names to human-readable collection prompts
            # so this message is never sent raw to the client.
            _FIELD_PROMPT: dict[str, str] = {
                "scheduled_start_at": "I still need the date and time.",
                "booking_type": "I need to know if you want incall or outcall.",
                "duration_minutes": "I still need the duration.",
                "outcall_address": "I still need your address (for outcalls).",
                "client_name": "I still need your name (you can skip this if you prefer).",
                "client_age": "I still need to confirm your age.",
                "client_ethnicity": "I still need your ethnicity.",
                "client_size_inches": "I still need to ask one more thing.",
                "alone_policy_confirmed": "I still need to confirm one more detail.",
            }
            missing = validation.next_required_field or "a required field"
            return booking, [_FIELD_PROMPT.get(missing, f"Still missing: {missing}.")]

        if booking.scheduled_start_at is None or booking.duration_minutes is None:
            return booking, ["Missing required scheduling fields."]

        booking_type_errors = self._validate_booking_type_present(booking)
        if booking_type_errors:
            return booking, booking_type_errors

        await self._ensure_outcall_advance_defaults(booking)

        outcall_errors = await self._validate_outcall_requirements(booking)
        if outcall_errors:
            return booking, outcall_errors

        # Re-check availability
        avail = await self.availability.check(
            worker_id=booking.worker_id,
            proposed_start=booking.scheduled_start_at,
            duration_minutes=booking.duration_minutes,
            exclude_booking_id=booking_id,
        )
        if not avail.available:
            return booking, [avail.conflict_reason or "Slot unavailable."]

        booking.status = BookingStatus.PENDING_REVIEW
        booking.awaiting_review_from = reviewer
        await self.repo.save(booking)

        # Update session state
        session = await self.session_repo.get_by_id(booking.session_id)
        if session:
            await self.session_repo.update_state(session, ConversationState.WAITING_REVIEW)

        await self.audit.log(
            entity_type="booking",
            entity_id=booking_id,
            event_type="submitted_for_review",
            actor_type=actor_type,
            actor_ref=actor_ref,
            metadata={"reviewer": reviewer.value},
        )
        await self.notifications.create_review_notifications(booking)
        admin_event_stream.publish(
            "booking.submitted_for_review",
            {
                "booking_id": str(booking.id),
                "status": booking.status.value,
                "awaiting_review_from": booking.awaiting_review_from.value,
            },
        )
        return booking, []

    async def set_status(
        self,
        booking_id: uuid.UUID,
        status: BookingStatus,
        actor_type: ActorType,
        actor_ref: str | None = None,
        note: str | None = None,
    ) -> tuple[Any, list[str]]:
        """
        Controlled status transition with audit log.
        Validates allowed transitions.
        """
        booking = await self.repo.get_by_id(booking_id)
        if not booking:
            return None, ["Booking not found."]

        if booking.status == status:
            return booking, []

        allowed = self._allowed_transitions(booking.status)
        if status not in allowed:
            return booking, [
                f"Transition {booking.status} -> {status} is not allowed. "
                f"Allowed: {[s.value for s in allowed]}"
            ]

        now = datetime.now(UTC)
        booking.status = status

        if status == BookingStatus.CONFIRMED:
            booking.confirmed_at = now
            if booking.scheduled_start_at is None or booking.duration_minutes is None:
                booking.status = BookingStatus.PENDING_REVIEW
                booking.confirmed_at = None
                return booking, ["Booking is missing scheduling data for confirmation."]
            # Re-check availability one final time
            avail = await self.availability.check(
                worker_id=booking.worker_id,
                proposed_start=booking.scheduled_start_at,
                duration_minutes=booking.duration_minutes,
                exclude_booking_id=booking_id,
            )
            if not avail.available:
                booking.status = BookingStatus.PENDING_REVIEW  # rollback
                return booking, [avail.conflict_reason or "Slot conflict at confirmation."]

            confirmation_errors = await self._validate_confirmation_requirements(booking)
            if confirmation_errors:
                booking.status = BookingStatus.PENDING_REVIEW
                booking.confirmed_at = None
                return booking, confirmation_errors

            await self._update_session_on_terminal(booking, ConversationState.IDLE)

        elif status == BookingStatus.REJECTED:
            await self._update_session_on_terminal(booking, ConversationState.IDLE)

        elif status == BookingStatus.CANCELLED:
            booking.cancelled_at = now
            await self._update_session_on_terminal(booking, ConversationState.IDLE)

        elif status == BookingStatus.COMPLETED:
            booking.completed_at = now
            await self._update_session_on_terminal(booking, ConversationState.IDLE)

        await self.repo.save(booking)
        await self.audit.log(
            entity_type="booking",
            entity_id=booking_id,
            event_type=f"status_changed:{status.value}",
            actor_type=actor_type,
            actor_ref=actor_ref,
            metadata={"note": note or ""},
        )
        await self.notifications.create_booking_decision_notifications(
            booking=booking,
            actor_type=actor_type,
            note=note,
        )
        metrics.incr("booking_status_transitions_total")
        if status == BookingStatus.CONFIRMED:
            await self.notifications.schedule_booking_reminders(booking.id)
        # Decision message is sent by the router as a BackgroundTask so it
        # never blocks or rolls back the status-change HTTP response.
        admin_event_stream.publish(
            "booking.status_changed",
            {
                "booking_id": str(booking.id),
                "worker_id": str(booking.worker_id),
                "status": booking.status.value,
                "actor_type": actor_type.value,
                "actor_ref": actor_ref,
                "note": note or "",
            },
        )
        return booking, []

    async def complete_early(
        self,
        booking_id: uuid.UUID,
        actor_ref: str | None = None,
    ) -> tuple[Any, list[str]]:
        return await self.set_status(
            booking_id=booking_id,
            status=BookingStatus.COMPLETED,
            actor_type=ActorType.WORKER,
            actor_ref=actor_ref,
            note="completed_early",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _allowed_transitions(self, current: BookingStatus) -> list[BookingStatus]:
        transitions: dict[BookingStatus, list[BookingStatus]] = {
            BookingStatus.DRAFT: [BookingStatus.PENDING_REVIEW, BookingStatus.CANCELLED],
            BookingStatus.PENDING_REVIEW: [
                BookingStatus.CONFIRMED,
                BookingStatus.REJECTED,
                BookingStatus.CANCELLED,
            ],
            BookingStatus.CONFIRMED: [BookingStatus.COMPLETED, BookingStatus.CANCELLED],
            BookingStatus.REJECTED: [],
            BookingStatus.CANCELLED: [],
            BookingStatus.COMPLETED: [],
        }
        return transitions.get(current, [])

    async def _update_session_on_terminal(self, booking: Any, new_state: ConversationState) -> None:
        session = await self.session_repo.get_by_id(booking.session_id)
        if session:
            session.active_booking_id = None
            await self.session_repo.update_state(session, new_state)

    async def _build_agent_decision_instruction(self, booking: Any, status: BookingStatus) -> str:
        """Build a high-signal system instruction for admin booking decisions."""
        if booking.scheduled_start_at:
            try:
                start_label = booking.scheduled_start_at.astimezone(UTC).strftime(
                    "%A %d %B at %H:%M"
                )
            except Exception:
                start_label = str(booking.scheduled_start_at)
        else:
            start_label = "the booking"

        history = await MessageRepository(self.db).list_for_session(booking.session_id)
        recent_client_text = ""
        for msg in reversed(history):
            if (
                msg.direction == MessageDirection.INBOUND
                and msg.sender_type == SenderType.CLIENT
                and (msg.body or "").strip()
            ):
                recent_client_text = (msg.body or "").strip()
                break

        if len(recent_client_text) > 240:
            recent_client_text = f"{recent_client_text[:237]}..."

        if status == BookingStatus.CONFIRMED:
            decision_guidance = (
                f"The booking for {start_label} is now confirmed. "
                "Sound warm, positive, and natural."
            )
            decision_tag = "confirmed"
        elif status == BookingStatus.REJECTED:
            decision_guidance = (
                f"The booking for {start_label} is not available. "
                "Apologise warmly and invite a different time."
            )
            decision_tag = "rejected"
        else:
            decision_guidance = (
                f"The booking for {start_label} was cancelled. "
                "Be clear and caring, and invite rebooking when they want."
            )
            decision_tag = "cancelled"

        context_hint = ""
        if recent_client_text:
            context_hint = (
                " Keep continuity with the client's recent wording and tone. "
                f"Recent client message: \"{recent_client_text}\"."
            )

        return (
            f"[ADMIN ACTION: booking {decision_tag}] "
            f"{decision_guidance}{context_hint} "
            "Write only the outbound client message in Alysha's voice. "
            "Do not mention admin actions or internal steps. 1-2 lines max."
        )

    async def send_client_decision_message(self, booking: Any, status: BookingStatus) -> None:
        if status not in {BookingStatus.CONFIRMED, BookingStatus.REJECTED, BookingStatus.CANCELLED}:
            return

        client = await self.client_repo.get_by_id(booking.client_id)
        if client is None:
            return

        session = await self.session_repo.get_by_id(booking.session_id)
        if session is None or session.last_channel is None:
            return
        admin_instruction = await self._build_agent_decision_instruction(booking, status)

        # Route admin decisions through the client runtime facade so this path
        # remains isolated from worker-facing runtime behavior.
        from app.services.client_runtime_service import ClientRuntimeService
        from app.services.twilio_gateway import TwilioGateway

        worker_repo = WorkerRepository(self.db)
        worker = await worker_repo.get_active_worker()
        if worker is None:
            worker, _ = await worker_repo.get_or_create_default(
                name=settings.default_worker_name,
                timezone=settings.default_worker_timezone,
            )

        runtime = ClientRuntimeService(self.db)
        channel = session.last_channel
        reply = await runtime.generate_admin_decision_reply(
            session_id=session.id,
            client_id=client.id,
            worker_id=worker.id,
            channel=channel,
            decision_instruction=admin_instruction,
        )

        gateway = TwilioGateway()
        send_result = await gateway.send_client_message(
            to_phone_e164=client.phone_e164,
            channel=channel.value,
            text=reply.text,
        )

        message_repo = MessageRepository(self.db)
        outbound = Message(
            session_id=session.id,
            direction=MessageDirection.OUTBOUND,
            channel=channel,
            sender_type=SenderType.AGENT,
            body=reply.text,
            twilio_message_sid=send_result.sid,
            raw_payload={
                "decision_send": True,
                "booking_id": str(booking.id),
                "status": status.value,
                "dispatch": {
                    "ok": send_result.ok,
                    "sid": send_result.sid,
                    "stub": send_result.stub,
                    "error": send_result.error,
                },
            },
        )
        await message_repo.save(outbound)
        admin_event_stream.publish(
            "booking.decision_message_sent",
            {
                "booking_id": str(booking.id),
                "status": status.value,
                "message": reply.text,
            },
        )

    async def mark_incall_address_sent(
        self,
        booking_id: uuid.UUID,
        actor_type: ActorType,
        actor_ref: str | None = None,
    ) -> tuple[Any, list[str]]:
        booking = await self.repo.get_by_id(booking_id)
        if not booking:
            return None, ["Booking not found."]

        from app.models.enums import BookingType

        if booking.booking_type != BookingType.INCALL:
            return booking, ["Incall address can only be sent for incall bookings."]
        if booking.status != BookingStatus.CONFIRMED:
            return booking, ["Incall address can only be sent after booking confirmation."]
        if booking.incall_address_sent_at is not None:
            return booking, []

        booking.incall_address_sent_at = datetime.now(UTC)
        await self.repo.save(booking)
        await self.audit.log(
            entity_type="booking",
            entity_id=booking_id,
            event_type="incall_address_sent",
            actor_type=actor_type,
            actor_ref=actor_ref,
            metadata={},
        )
        admin_event_stream.publish(
            "booking.incall_address_sent",
            {
                "booking_id": str(booking.id),
                "incall_address_sent_at": booking.incall_address_sent_at.isoformat(),
            },
        )
        return booking, []

    async def _validate_outcall_requirements(self, booking: Any) -> list[str]:
        from app.models.enums import BookingType

        if booking.booking_type != BookingType.OUTCALL:
            return []

        errors: list[str] = []
        if not (booking.outcall_address or "").strip():
            errors.append("Outcall address is required for outcall bookings.")
        if booking.advance_required_gbp is None:
            errors.append("Advance amount is required for outcall bookings.")
        if booking.advance_required_gbp is not None and booking.advance_required_gbp <= 0:
            errors.append("Advance amount must be greater than 0 for outcall bookings.")
        return errors

    async def _validate_confirmation_requirements(self, booking: Any) -> list[str]:
        from app.models.enums import BookingType

        if booking.booking_type != BookingType.OUTCALL:
            return []

        if not booking.advance_received:
            return ["Outcall booking cannot be confirmed before advance is received."]
        has_receipt = await self.media.has_receipt_for_booking(booking.id)
        if not has_receipt:
            return ["Outcall booking cannot be confirmed without a receipt image."]
        return []

    def _validate_booking_type_present(self, booking: Any) -> list[str]:
        if booking.booking_type is None:
            return ["Booking type must be set to incall or outcall before review."]
        return []

    async def _ensure_outcall_advance_defaults(self, booking: Any) -> None:
        from app.models.enums import BookingType

        if booking.booking_type != BookingType.OUTCALL:
            return

        if booking.advance_required_gbp is not None:
            return

        booking.advance_required_gbp = Decimal("50")
        await self.repo.save(booking)
