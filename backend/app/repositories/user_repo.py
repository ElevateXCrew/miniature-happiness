import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def list_workers(self) -> list[User]:
        result = await self.db.execute(
            select(User).where(User.role == UserRole.WORKER).order_by(User.created_at)
        )
        return list(result.scalars().all())

    async def create_user(
        self,
        email: str,
        password_hash: str,
        role: UserRole,
        worker_id: uuid.UUID | None = None,
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            role=role,
            is_active=True,
            worker_id=worker_id,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def touch_login(self, user: User, refresh_jti: str) -> User:
        user.last_login_at = datetime.now(UTC)
        user.current_refresh_jti = refresh_jti
        await self.db.flush()
        return user

    async def update_refresh_jti(self, user: User, refresh_jti: str | None) -> User:
        user.current_refresh_jti = refresh_jti
        await self.db.flush()
        return user
