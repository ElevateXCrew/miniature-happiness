"""
Notification service: queues and dispatches notifications, schedules reminders.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.models.enums import (
    ActorType,
    BookingType,
    Channel,
    MessageDirection,
    NotificationChannel,
    NotificationStatus,
    NotificationTargetType,
    SenderType,
)
from app.models.message import Message
from app.models.notification import Notification
from app.repositories.booking_repo import BookingRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.event_stream import admin_event_stream
from app.services.twilio_gateway import TwilioGateway


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = NotificationRepository(db)
        self.booking_repo = BookingRepository(db)
        self.clients = ClientRepository(db)
        self.sessions = SessionRepository(db)
        self.workers = WorkerRepository(db)
        self.messages = MessageRepository(db)
        self.gateway = TwilioGateway()

    def _emit_notification_event(self, event_type: str, notif: Notification) -> None:
        admin_event_stream.publish(
            event_type,
            {
                "notification_id": str(notif.id),
                "booking_id": str(notif.booking_id) if notif.booking_id else None,
                "status": notif.status.value,
                "template_key": notif.template_key,
                "target_type": notif.target_type.value,
                "send_at": notif.send_at.isoformat(),
            },
        )

    async def _render_text(self, notif: Notification) -> str:
        payload = notif.payload if isinstance(notif.payload, dict) else {}
        booking_id = payload.get("booking_id")
        style_hint = payload.get("style_hint")
        if notif.template_key == "outbound_retry_message":
            text = str(payload.get("text") or "").strip()
            if text:
                return text
            return "Message from Alysha"
        if notif.template_key.startswith("booking_reminder"):
            return f"Reminder: booking {booking_id or ''} in 20 mins."
        if notif.template_key.startswith("booking_pending_review"):
            return f"Booking {booking_id or ''} is pending review."
        if notif.template_key.startswith("booking_confirmed"):
            return "Your booking is confirmed babe."
        if notif.template_key.startswith("booking_rejected"):
            return "Sorry babe, that slot isn't available now."
        if notif.template_key.startswith("booking_cancelled"):
            return "Booking cancelled babe."
        if style_hint == "i_am_about_to_arrive":
            return "I am about to arrive babe."
        if style_hint == "are_you_coming":
            return "Are you coming babe?"
        return f"Notification: {notif.template_key}"

    async def _resolve_destination(self, notif: Notification) -> tuple[str | None, str | None]:
        channel = None
        to_phone = None
        if notif.channel == NotificationChannel.WHATSAPP:
            channel = Channel.WHATSAPP.value
        elif notif.channel == NotificationChannel.SMS:
            channel = Channel.SMS.value

        if channel is None:
            return None, None

        if notif.target_type == NotificationTargetType.CLIENT:
            try:
                client = await self.clients.get_by_id(uuid.UUID(notif.target_ref))
            except ValueError:
                client = None
            if client is None:
                return channel, None
            to_phone = client.phone_e164
            return channel, to_phone

        if notif.target_type == NotificationTargetType.WORKER:
            return None, None

        return None, None

    async def queue_outbound_retry(
        self,
        *,
        client_id: uuid.UUID,
        channel: Channel,
        text: str,
        context: dict[str, Any] | None,
        error: str | None,
        source: str,
    ) -> Notification:
        mapped_notification_channel = (
            NotificationChannel.WHATSAPP if channel == Channel.WHATSAPP else NotificationChannel.SMS
        )
        retry_notif = await self.create(
            target_type=NotificationTargetType.CLIENT,
            target_ref=str(client_id),
            template_key="outbound_retry_message",
            payload={
                "text": text,
                "context": context or {},
                "source": source,
            },
            send_at=datetime.now(UTC),
            channel=mapped_notification_channel,
        )
        await self.mark_failed(
            retry_notif.id,
            error=error,
            allow_retry=True,
        )
        return retry_notif

    async def dispatch_due_notifications(self, *, now: datetime | None = None) -> dict[str, int]:
        reference_now = now or datetime.now(UTC)
        due = await self.repo.list_queued_due(reference_now)
        sent = 0
        failed = 0
        dead_lettered = 0

        for notif in due:
            channel, to_phone = await self._resolve_destination(notif)
            if channel is None:
                notif.status = NotificationStatus.SENT
                notif.sent_at = datetime.now(UTC)
                await self.repo.save(notif)
                sent += 1
                continue

            if not to_phone:
                await self.mark_failed(
                    notif.id,
                    error="Destination unavailable",
                    allow_retry=False,
                )
                dead_lettered += 1
                continue

            text = await self._render_text(notif)
            send_result = await self.gateway.send_client_message(
                to_phone_e164=to_phone,
                channel=channel,
                text=text,
            )
            if send_result.ok:
                await self.mark_sent(notif.id)
                sent += 1
            else:
                transitioned = await self.mark_failed(
                    notif.id,
                    error=send_result.error,
                    allow_retry=True,
                )
                if transitioned == NotificationStatus.DEAD_LETTER:
                    dead_lettered += 1
                else:
                    failed += 1

        return {
            "due": len(due),
            "sent": sent,
            "failed": failed,
            "dead_lettered": dead_lettered,
        }

    async def create(
        self,
        target_type: NotificationTargetType,
        target_ref: str,
        template_key: str,
        payload: dict[str, Any],
        send_at: datetime,
        booking_id: uuid.UUID | None = None,
        channel: NotificationChannel = NotificationChannel.IN_APP,
    ) -> Notification:
        notification = Notification(
            booking_id=booking_id,
            target_type=target_type,
            target_ref=target_ref,
            channel=channel,
            template_key=template_key,
            payload=payload,
            status=NotificationStatus.QUEUED,
            send_at=send_at,
        )
        saved = await self.repo.save(notification)
        self._emit_notification_event("notification.created", saved)
        return saved

    async def schedule_booking_reminders(
        self,
        booking_id: uuid.UUID,
        minutes_before: int = settings.reminder_minutes_before,
    ) -> list[Notification]:
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking or not booking.scheduled_start_at:
            return []

        send_at = booking.scheduled_start_at - timedelta(minutes=minutes_before)
        now = datetime.now(UTC)
        if send_at <= now:
            # Too late to schedule; fire immediately
            send_at = now

        is_outcall = booking.booking_type == BookingType.OUTCALL
        existing = await self.repo.list_for_booking(booking_id)
        if any(
            n.template_key
            in {
                "booking_reminder_admin",
                "booking_reminder_worker_outcall",
                "booking_reminder_worker_incall",
                "booking_reminder_client_outcall",
                "booking_reminder_client_incall",
            }
            for n in existing
        ):
            return []

        created: list[Notification] = []

        # Admin reminder
        admin_notif = await self.create(
            target_type=NotificationTargetType.ADMIN,
            target_ref="admin",
            template_key="booking_reminder_admin",
            payload={
                "booking_id": str(booking_id),
                "booking_type": booking.booking_type.value if booking.booking_type else None,
                "style_hint": "ops_t_minus_20",
            },
            send_at=send_at,
            booking_id=booking_id,
            channel=NotificationChannel.IN_APP,
        )
        created.append(admin_notif)

        # Worker reminder
        worker_template = (
            "booking_reminder_worker_outcall" if is_outcall else "booking_reminder_worker_incall"
        )
        worker_notif = await self.create(
            target_type=NotificationTargetType.WORKER,
            target_ref=str(booking.worker_id),
            template_key=worker_template,
            payload={
                "booking_id": str(booking_id),
                "booking_type": booking.booking_type.value if booking.booking_type else None,
                "style_hint": "i_am_about_to_arrive" if is_outcall else "are_you_coming",
            },
            send_at=send_at,
            booking_id=booking_id,
            channel=NotificationChannel.WHATSAPP,
        )
        created.append(worker_notif)

        # Client reminder
        client_template = (
            "booking_reminder_client_outcall" if is_outcall else "booking_reminder_client_incall"
        )
        client_channel = (
            NotificationChannel.WHATSAPP
            if booking.session
            and hasattr(booking.session, "last_channel")
            and str(booking.session.last_channel) == "whatsapp"
            else NotificationChannel.SMS
        )
        client_notif = await self.create(
            target_type=NotificationTargetType.CLIENT,
            target_ref=str(booking.client_id),
            template_key=client_template,
            payload={
                "booking_id": str(booking_id),
                "booking_type": booking.booking_type.value if booking.booking_type else None,
                "style_hint": "i_am_about_to_arrive" if is_outcall else "are_you_coming",
            },
            send_at=send_at,
            booking_id=booking_id,
            channel=client_channel,
        )
        created.append(client_notif)

        return created

    async def mark_sent(self, notification_id: uuid.UUID) -> None:
        notif = await self.repo.get_by_id(notification_id)
        if notif:
            notif.status = NotificationStatus.SENT
            notif.sent_at = datetime.now(UTC)
            notif.last_error = None
            notif.next_retry_at = None
            saved = await self.repo.save(notif)
            self._emit_notification_event("notification.status_changed", saved)
            metrics.incr("notifications_sent_total")

    async def mark_failed(
        self,
        notification_id: uuid.UUID,
        *,
        error: str | None = None,
        allow_retry: bool = True,
    ) -> NotificationStatus | None:
        notif = await self.repo.get_by_id(notification_id)
        if not notif:
            return None

        notif.last_error = error
        max_retries = max(0, settings.outbound_retry_max_attempts)
        if allow_retry and notif.retry_count < max_retries:
            notif.retry_count += 1
            backoff = max(1, settings.outbound_retry_backoff_seconds) * (
                2 ** (notif.retry_count - 1)
            )
            notif.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff)
            notif.send_at = notif.next_retry_at
            notif.status = NotificationStatus.RETRY_PENDING
            metrics.incr("notifications_retry_scheduled_total")
        else:
            notif.status = NotificationStatus.DEAD_LETTER
            metrics.incr("notifications_dead_letter_total")

        await self.repo.save(notif)
        self._emit_notification_event("notification.status_changed", notif)
        metrics.incr("notifications_failed_total")
        return notif.status

    async def create_review_notifications(self, booking: Any) -> list[Notification]:
        now = datetime.now(UTC)
        notifications: list[Notification] = []

        notifications.append(
            await self.create(
                target_type=NotificationTargetType.ADMIN,
                target_ref="admin",
                template_key="booking_pending_review_admin",
                payload={
                    "booking_id": str(booking.id),
                    "status": booking.status.value,
                    "awaiting_review_from": booking.awaiting_review_from.value,
                },
                send_at=now,
                booking_id=booking.id,
                channel=NotificationChannel.IN_APP,
            )
        )
        notifications.append(
            await self.create(
                target_type=NotificationTargetType.WORKER,
                target_ref=str(booking.worker_id),
                template_key="booking_pending_review_worker",
                payload={"booking_id": str(booking.id), "status": booking.status.value},
                send_at=now,
                booking_id=booking.id,
                channel=NotificationChannel.WHATSAPP,
            )
        )
        return notifications

    async def create_booking_decision_notifications(
        self,
        booking: Any,
        actor_type: ActorType,
        note: str | None = None,
    ) -> list[Notification]:
        status = booking.status.value.lower()
        if status not in {"confirmed", "rejected", "cancelled", "completed"}:
            return []

        now = datetime.now(UTC)
        return [
            await self.create(
                target_type=NotificationTargetType.ADMIN,
                target_ref="admin",
                template_key=f"booking_{status}_admin",
                payload={
                    "booking_id": str(booking.id),
                    "status": booking.status.value,
                    "actor_type": actor_type.value,
                    "note": note or "",
                },
                send_at=now,
                booking_id=booking.id,
                channel=NotificationChannel.IN_APP,
            )
        ]

    async def schedule_due_booking_reminders(
        self,
        *,
        now: datetime | None = None,
        minutes_before: int = settings.reminder_minutes_before,
    ) -> dict[str, int]:
        reference_now = now or datetime.now(UTC)
        cutoff = reference_now + timedelta(minutes=minutes_before)
        candidates = await self.booking_repo.list_confirmed_starting_before(cutoff)

        created_total = 0
        for booking in candidates:
            created = await self.schedule_booking_reminders(
                booking_id=booking.id,
                minutes_before=minutes_before,
            )
            created_total += len(created)

        return {
            "bookings_considered": len(candidates),
            "notifications_created": created_total,
        }

    async def send_client_message(
        self,
        client_id: uuid.UUID,
        channel: str,
        text: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            return {"ok": False, "error": "Client not found."}

        worker = await self.workers.get_active_worker()
        if worker is None:
            worker, _ = await self.workers.get_or_create_default(
                name="Alysha", timezone="Europe/London"
            )

        mapped_channel = Channel.WHATSAPP if channel == "whatsapp" else Channel.SMS
        session, _ = await self.sessions.get_or_create(client.id, worker.id, mapped_channel)
        send_result = await self.gateway.send_client_message(
            to_phone_e164=client.phone_e164,
            channel=mapped_channel.value,
            text=text,
        )

        outbound = Message(
            session_id=session.id,
            direction=MessageDirection.OUTBOUND,
            channel=mapped_channel,
            sender_type=SenderType.AGENT,
            body=text,
            twilio_message_sid=send_result.sid,
            raw_payload={
                "decision_send": True,
                "context": context,
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
            await self.queue_outbound_retry(
                client_id=client.id,
                channel=mapped_channel,
                text=text,
                context=context,
                error=send_result.error,
                source="send_client_message",
            )
        return {"ok": send_result.ok, "error": send_result.error, "message_id": str(outbound.id)}
