import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.events import is_worker_event_visible
from app.models.booking import Booking
from app.models.client import Client
from app.models.conversation_session import ConversationSession
from app.models.enums import (
    BookingStatus,
    BookingType,
    Channel,
    NotificationChannel,
    NotificationTargetType,
    SectionKey,
    UserRole,
)
from app.models.notification import Notification
from app.models.user import User
from app.models.worker import Worker
from app.services.auth_service import AuthService, hash_password
from app.services.event_stream import admin_event_stream
from app.services.notification_service import NotificationService
from app.services.permission_service import PermissionService
from app.services.twilio_gateway import OutboundSendResult, TwilioGateway


@pytest.mark.asyncio
async def test_admin_and_worker_stream_role_guards(client: AsyncClient, db: AsyncSession) -> None:
    worker = Worker(name='Alysha Worker', timezone='Europe/London', is_active=True)
    db.add(worker)
    await db.flush()

    worker_user = User(
        email=f"worker-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password('worker123'),
        role=UserRole.WORKER,
        is_active=True,
        worker_id=worker.id,
    )
    db.add(worker_user)
    await db.flush()

    worker_access_token = (await AuthService(db).issue_token_pair(worker_user))['access_token']

    worker_on_admin_stream = await client.get(
        '/events/admin/stream',
        headers={'Authorization': f'Bearer {worker_access_token}'},
    )
    assert worker_on_admin_stream.status_code == 403

    admin_on_worker_stream = await client.get('/events/worker/stream')
    assert admin_on_worker_stream.status_code == 403


@pytest.mark.asyncio
async def test_worker_stream_receives_own_permission_updates_only(
    db: AsyncSession,
) -> None:
    first_worker = Worker(name='Alysha One', timezone='Europe/London', is_active=True)
    second_worker = Worker(name='Alysha Two', timezone='Europe/London', is_active=True)
    db.add_all([first_worker, second_worker])
    await db.flush()

    first_worker_user = User(
        email=f"worker-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password('worker123'),
        role=UserRole.WORKER,
        is_active=True,
        worker_id=first_worker.id,
    )
    second_worker_user = User(
        email=f"worker-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password('worker123'),
        role=UserRole.WORKER,
        is_active=True,
        worker_id=second_worker.id,
    )
    admin_user = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password('admin123'),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add_all([first_worker_user, second_worker_user, admin_user])
    await db.flush()

    permission_service = PermissionService(db)

    await permission_service.set_worker_permissions(
        worker_user_id=second_worker_user.id,
        section_updates={SectionKey.SCHEDULE: False},
        updated_by_user=admin_user,
    )
    await permission_service.set_worker_permissions(
        worker_user_id=first_worker_user.id,
        section_updates={SectionKey.LIVE_CHAT: False},
        updated_by_user=admin_user,
    )

    first_update_visible = is_worker_event_visible(
        str(first_worker_user.id),
        'worker.permissions.updated',
        {
            'worker_user_id': str(first_worker_user.id),
            'sections': {SectionKey.LIVE_CHAT.value: False},
        },
    )
    assert first_update_visible is True

    second_update_visible = is_worker_event_visible(
        str(first_worker_user.id),
        'worker.permissions.updated',
        {
            'worker_user_id': str(second_worker_user.id),
            'sections': {SectionKey.SCHEDULE.value: False},
        },
    )
    assert second_update_visible is False

    different_event_hidden = is_worker_event_visible(
        str(first_worker_user.id),
        'booking.status_changed',
        {
            'worker_user_id': str(first_worker_user.id),
        },
    )
    assert different_event_hidden is False


@pytest.mark.asyncio
async def test_admin_stream_emits_booking_status_changed_on_approve(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    created_client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, created_client])
    await db.flush()

    session = ConversationSession(
        client_id=created_client.id,
        worker_id=worker.id,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=created_client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=26,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    current_history = admin_event_stream.history_since(None)
    last_event_id = current_history[-1].id if current_history else None

    approve = await client.post(f"/admin/bookings/{booking.id}/approve")
    assert approve.status_code == 200

    new_events = admin_event_stream.history_since(last_event_id)
    matching = [
        event
        for event in new_events
        if event.type == "booking.status_changed"
        and event.payload.get("booking_id") == str(booking.id)
        and event.payload.get("status") == BookingStatus.CONFIRMED.value
    ]
    assert matching


@pytest.mark.asyncio
async def test_admin_stream_emits_notification_created_and_status_changed(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    created_client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, created_client])
    await db.flush()

    async def _always_ok(
        self: TwilioGateway, *, to_phone_e164: str, channel: str, text: str
    ) -> OutboundSendResult:
        return OutboundSendResult(ok=True, sid="SM_OK_001", error=None)

    monkeypatch.setattr(TwilioGateway, "send_client_message", _always_ok)

    current_history = admin_event_stream.history_since(None)
    last_event_id = current_history[-1].id if current_history else None

    svc = NotificationService(db)
    notif = await svc.create(
        target_type=NotificationTargetType.CLIENT,
        target_ref=str(created_client.id),
        template_key="outbound_retry_message",
        payload={"text": "Test dispatch"},
        send_at=datetime.now(UTC) - timedelta(minutes=1),
        channel=NotificationChannel.SMS,
    )

    dispatch = await client.post("/notifications/dispatch/run")
    assert dispatch.status_code == 200
    assert dispatch.json()["sent"] >= 1

    refreshed = await db.get(Notification, notif.id)
    assert refreshed is not None
    assert refreshed.status.value == "sent"

    new_events = admin_event_stream.history_since(last_event_id)
    created_events = [
        event
        for event in new_events
        if event.type == "notification.created"
        and event.payload.get("notification_id") == str(notif.id)
    ]
    status_events = [
        event
        for event in new_events
        if event.type == "notification.status_changed"
        and event.payload.get("notification_id") == str(notif.id)
        and event.payload.get("status") == "sent"
    ]
    assert created_events
    assert status_events
