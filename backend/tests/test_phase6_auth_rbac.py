import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.enums import SectionKey, UserRole
from app.models.user import User
from app.models.worker import Worker
from app.services.auth_service import AuthService, hash_password


@pytest.mark.asyncio
async def test_auth_login_refresh_logout_flow(client: AsyncClient, db: AsyncSession) -> None:
    user = User(
        email=f"worker-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password("worker123"),
        role=UserRole.WORKER,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    login_res = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "worker123"},
    )
    assert login_res.status_code == 200
    login_body = login_res.json()
    assert login_body["token_type"] == "bearer"

    refresh_res = await client.post(
        "/auth/refresh",
        json={"refresh_token": login_body["refresh_token"]},
    )
    assert refresh_res.status_code == 200
    refreshed = refresh_res.json()

    me_res = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {refreshed['access_token']}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == user.email

    logout_res = await client.post(
        "/auth/logout",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert logout_res.status_code == 200

    invalid_after_logout = await client.post(
        "/auth/refresh",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert invalid_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_ui_sections_admin_and_worker(client: AsyncClient, db: AsyncSession) -> None:
    admin_sections = await client.get("/ui/sections")
    assert admin_sections.status_code == 200
    assert all(admin_sections.json()["sections"].values())

    worker = Worker(name="Alysha Worker", timezone="Europe/London", is_active=True)
    db.add(worker)
    await db.flush()

    worker_user = User(
        email=f"worker-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password("worker123"),
        role=UserRole.WORKER,
        is_active=True,
        worker_id=worker.id,
    )
    db.add(worker_user)
    await db.flush()

    worker_token = (await AuthService(db).issue_token_pair(worker_user))["access_token"]
    worker_sections = await client.get(
        "/ui/sections",
        headers={"Authorization": f"Bearer {worker_token}"},
    )
    assert worker_sections.status_code == 200
    assert all(worker_sections.json()["sections"].values())


@pytest.mark.asyncio
async def test_admin_can_toggle_worker_section_and_worker_gets_403(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha Worker", timezone="Europe/London", is_active=True)
    db.add(worker)
    await db.flush()

    worker_user = User(
        email=f"worker-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password("worker123"),
        role=UserRole.WORKER,
        is_active=True,
        worker_id=worker.id,
    )
    db.add(worker_user)
    await db.flush()

    update_res = await client.put(
        f"/admin/users/{worker_user.id}/section-permissions",
        json={"sections": {SectionKey.LIVE_CHAT.value: False}},
    )
    assert update_res.status_code == 200
    assert update_res.json()["sections"][SectionKey.LIVE_CHAT.value] is False

    worker_token = (await AuthService(db).issue_token_pair(worker_user))["access_token"]
    blocked_res = await client.post(
        "/worker/messages",
        json={"worker_id": str(worker.id), "message_text": "hello"},
        headers={"Authorization": f"Bearer {worker_token}"},
    )
    assert blocked_res.status_code == 403

    audit_result = await db.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "user",
            AuditEvent.entity_id == worker_user.id,
            AuditEvent.event_type == "worker_section_permissions.updated",
        )
    )
    assert audit_result.scalars().first() is not None


@pytest.mark.asyncio
async def test_invalid_token_is_unauthorized(client: AsyncClient) -> None:
    res = await client.get("/auth/me", headers={"Authorization": "Bearer invalid"})
    assert res.status_code == 401
