"""
Test configuration and fixtures.
Uses an in-memory SQLite database (via aiosqlite) for fast unit tests
without requiring a live PostgreSQL instance.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.engine import get_db
from app.main import app
from app.models import *  # noqa: F401, F403 — registers all models
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthService, hash_password

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    # Create a default authenticated admin user for protected API tests.
    admin_user = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=hash_password("admin123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin_user)
    await db.flush()

    token_pair = await AuthService(db).issue_token_pair(admin_user)

    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token_pair['access_token']}"
        yield ac
    app.dependency_overrides.clear()


# --- Shared test data factories ---


def make_worker_id() -> uuid.UUID:
    return uuid.uuid4()


def make_client_id() -> uuid.UUID:
    return uuid.uuid4()
