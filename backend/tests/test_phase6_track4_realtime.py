import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.events import is_worker_event_visible
from app.models.enums import SectionKey, UserRole
from app.models.user import User
from app.models.worker import Worker
from app.services.auth_service import AuthService, hash_password
from app.services.permission_service import PermissionService


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
