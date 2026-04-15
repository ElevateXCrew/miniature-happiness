"""
Alysha Booking Assistant — FastAPI application entry point.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, events, health, media, notifications, worker
from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.db.engine import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting Alysha Booking Assistant", env=settings.app_env)
    await _seed_default_worker()
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
    app.include_router(admin.router)
    app.include_router(worker.router)
    app.include_router(media.router)
    app.include_router(notifications.router)
    app.include_router(events.router)

    return app


app = create_app()
