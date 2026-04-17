"""
Alysha Booking Assistant — FastAPI application entry point.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    admin,
    agent,
    auth,
    events,
    health,
    media,
    metrics,
    notifications,
    twilio,
    ui,
    worker,
)
from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.db.engine import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting Alysha Booking Assistant", env=settings.app_env)
    await _seed_default_worker()
    await _seed_default_users()
    yield
    logger.info("Shutting down")
    await engine.dispose()


async def _seed_default_worker() -> None:
    """Ensure the default worker (Alysha) exists in the DB on startup."""
    from app.db.engine import AsyncSessionLocal
    from app.repositories.worker_repo import WorkerRepository

    async with AsyncSessionLocal() as db:
        try:
            repo = WorkerRepository(db)
            worker_obj, created = await repo.get_or_create_default(
                name=settings.default_worker_name,
                timezone=settings.default_worker_timezone,
            )
            await db.commit()
            if created:
                logger.info("Seeded default worker", name=worker_obj.name, id=str(worker_obj.id))
            else:
                logger.info("Default worker exists", name=worker_obj.name, id=str(worker_obj.id))
        except Exception as e:
            logger.error("Failed to seed default worker", error=str(e))
            await db.rollback()


async def _seed_default_users() -> None:
    """Ensure default admin/worker users exist in the DB on startup."""
    from app.db.engine import AsyncSessionLocal
    from app.models.enums import UserRole
    from app.repositories.user_repo import UserRepository
    from app.repositories.worker_repo import WorkerRepository
    from app.services.auth_service import hash_password

    async with AsyncSessionLocal() as db:
        try:
            user_repo = UserRepository(db)
            worker_repo = WorkerRepository(db)
            worker = await worker_repo.get_active_worker()
            worker_id = UUID(str(worker.id)) if worker else None

            admin = await user_repo.get_by_email(settings.seed_admin_email)
            if not admin:
                admin = await user_repo.create_user(
                    email=settings.seed_admin_email,
                    password_hash=hash_password(settings.seed_admin_password),
                    role=UserRole.ADMIN,
                )
                logger.info("Seeded default admin user", email=admin.email, id=str(admin.id))

            worker_user = await user_repo.get_by_email(settings.seed_worker_email)
            if not worker_user:
                worker_user = await user_repo.create_user(
                    email=settings.seed_worker_email,
                    password_hash=hash_password(settings.seed_worker_password),
                    role=UserRole.WORKER,
                    worker_id=worker_id,
                )
                logger.info(
                    "Seeded default worker user",
                    email=worker_user.email,
                    id=str(worker_user.id),
                )
            elif worker and worker_user.worker_id is None:
                worker_user.worker_id = worker_id

            await db.commit()
        except Exception as e:
            logger.error("Failed to seed default users", error=str(e))
            await db.rollback()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Alysha Booking Assistant API",
        version="0.1.0",
        description="AI-powered booking assistant backend for Alysha",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(ui.router)
    app.include_router(admin.router)
    app.include_router(worker.router)
    app.include_router(media.router)
    app.include_router(notifications.router)
    app.include_router(metrics.router)
    app.include_router(events.router)
    app.include_router(twilio.router)
    app.include_router(agent.router)

    return app


app = create_app()
