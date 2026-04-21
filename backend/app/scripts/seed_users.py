"""
Seed admin and worker users for development.

Usage (from backend/ directory):
    python -m app.scripts.seed_users

Environment variables (same as backend):
    DATABASE_URL   — PostgreSQL DSN (required)
    ADMIN_EMAIL / SEED_ADMIN_EMAIL       — default: admin@alysha.local
    ADMIN_PASSWORD / SEED_ADMIN_PASSWORD — default: admin123
    WORKER_EMAIL / SEED_WORKER_EMAIL     — default: worker@alysha.local
    WORKER_PASSWORD / SEED_WORKER_PASSWORD — default: worker123
"""

import asyncio
import os

# ---- ensure backend package is importable when run as module ----


async def main() -> None:
    # Import lazily so we don't drag in deps before path is set
    from app.db.engine import AsyncSessionLocal
    from app.models.enums import UserRole
    from app.repositories.user_repo import UserRepository
    from app.repositories.worker_repo import WorkerRepository
    from app.services.auth_service import hash_password

    admin_email = os.getenv(
        "ADMIN_EMAIL",
        os.getenv("SEED_ADMIN_EMAIL", "admin@alysha.local"),
    )
    admin_password = os.getenv(
        "ADMIN_PASSWORD",
        os.getenv("SEED_ADMIN_PASSWORD", "admin123"),
    )
    worker_email = os.getenv(
        "WORKER_EMAIL",
        os.getenv("SEED_WORKER_EMAIL", "worker@alysha.local"),
    )
    worker_password = os.getenv(
        "WORKER_PASSWORD",
        os.getenv("SEED_WORKER_PASSWORD", "worker123"),
    )
    worker_name = os.getenv("DEFAULT_WORKER_NAME", "Alysha")
    worker_timezone = os.getenv("DEFAULT_WORKER_TIMEZONE", "Europe/London")

    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)
        worker_repo = WorkerRepository(db)

        worker_obj, worker_created = await worker_repo.get_or_create_default(
            name=worker_name,
            timezone=worker_timezone,
        )
        if worker_created:
            print(f"[seed] Created worker profile: {worker_obj.name} (id={worker_obj.id})")
        else:
            print(f"[seed] Worker profile already exists: {worker_obj.name} (id={worker_obj.id})")

        # Check if admin already exists
        admin_existing = await user_repo.get_by_email(admin_email)
        if admin_existing:
            print(
                f"[seed] Admin user already exists: {admin_existing.email} "
                f"(id={admin_existing.id})"
            )
        else:
            admin_user = await user_repo.create_user(
                email=admin_email,
                password_hash=hash_password(admin_password),
                role=UserRole.ADMIN,
            )
            print(f"[seed] Created admin: {admin_user.email} (id={admin_user.id})")

        worker_existing = await user_repo.get_by_email(worker_email)
        if worker_existing:
            if worker_existing.worker_id is None:
                worker_existing.worker_id = worker_obj.id
                print(
                    f"[seed] Linked existing worker user to worker profile: "
                    f"{worker_existing.email} -> {worker_obj.id}"
                )
            else:
                print(
                    f"[seed] Worker user already exists: {worker_existing.email} "
                    f"(id={worker_existing.id})"
                )
        else:
            worker_user = await user_repo.create_user(
                email=worker_email,
                password_hash=hash_password(worker_password),
                role=UserRole.WORKER,
                worker_id=worker_obj.id,
            )
            print(f"[seed] Created worker user: {worker_user.email} (id={worker_user.id})")

        await db.commit()

    print("[seed] Done. Use the credentials above to log in to admin/worker panels.")


if __name__ == "__main__":
    asyncio.run(main())
