"""
Seed an admin user and an optional worker user for development.

Usage (from backend/ directory):
    python -m app.scripts.seed_users

Environment variables (same as backend):
    DATABASE_URL   — PostgreSQL DSN (required)
    ADMIN_EMAIL    — default: admin@alysha.local
    ADMIN_PASSWORD — default: changeme123
"""

import asyncio
import os

# ---- ensure backend package is importable when run as module ----


async def main() -> None:
    # Import lazily so we don't drag in deps before path is set
    from app.db.engine import AsyncSessionLocal
    from app.models.enums import UserRole
    from app.repositories.user_repo import UserRepository
    from app.services.auth_service import hash_password

    admin_email = os.getenv("ADMIN_EMAIL", "admin@alysha.local")
    admin_password = os.getenv("ADMIN_PASSWORD", "changeme123")

    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)

        # Check if admin already exists
        existing = await user_repo.get_by_email(admin_email)
        if existing:
            print(f"[seed] Admin user already exists: {existing.email} (id={existing.id})")
        else:
            user = await user_repo.create_user(
                email=admin_email,
                password_hash=hash_password(admin_password),
                role=UserRole.ADMIN,
            )
            await db.commit()
            print(f"[seed] Created admin: {user.email} (id={user.id})")

    print("[seed] Done. Use the credentials above to log in to the admin panel.")


if __name__ == "__main__":
    asyncio.run(main())
