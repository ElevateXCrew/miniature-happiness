"""Realtime SSE streams for admin and worker panels."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies.auth import require_role
from app.models.enums import UserRole
from app.models.user import User
from app.services.event_stream import admin_event_stream

router = APIRouter(tags=["events"])


def _encode_sse(event_id: int | None, payload: dict[str, object]) -> str:
    serialized = json.dumps(payload)
    if event_id is None:
        return f"data: {serialized}\n\n"
    return f"id: {event_id}\ndata: {serialized}\n\n"


def is_worker_event_visible(
    worker_user_id: str,
    worker_id: str | None,
    event_type: str,
    payload: dict[str, object],
) -> bool:
    if event_type == "worker.permissions.updated":
        return payload.get("worker_user_id") == worker_user_id
    if event_type in {"worker.chat_reply", "worker.operation.completed"}:
        return payload.get("worker_user_id") == worker_user_id
    if event_type == "booking.status_changed":
        if worker_id is None:
            return False
        return payload.get("worker_id") == worker_id
    return False


@router.get("/events/admin/stream")
async def admin_event_stream_endpoint(
    request: Request,
    _: object = Depends(require_role(UserRole.ADMIN)),
) -> StreamingResponse:
    last_event_id: int | None = None
    raw_last_id = request.headers.get("last-event-id")
    if raw_last_id and raw_last_id.isdigit():
        last_event_id = int(raw_last_id)

    async def generator() -> AsyncIterator[str]:
        for event in admin_event_stream.history_since(last_event_id):
            yield _encode_sse(event.id, event.to_dict())

        queue = admin_event_stream.subscribe()
        yield _encode_sse(None, {"type": "admin_stream.connected"})

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _encode_sse(event.id, event.to_dict())
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            admin_event_stream.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.get("/events/worker/stream")
async def worker_event_stream_endpoint(
    request: Request,
    current_user: User = Depends(require_role(UserRole.WORKER)),
) -> StreamingResponse:
    last_event_id: int | None = None
    raw_last_id = request.headers.get("last-event-id")
    if raw_last_id and raw_last_id.isdigit():
        last_event_id = int(raw_last_id)

    worker_user_id = str(current_user.id)
    worker_id = str(current_user.worker_id) if current_user.worker_id is not None else None

    async def generator() -> AsyncIterator[str]:
        for event in admin_event_stream.history_since(last_event_id):
            payload_obj = event.to_dict()
            if is_worker_event_visible(
                worker_user_id,
                worker_id,
                event.type,
                payload_obj.get("payload", {}),
            ):
                yield _encode_sse(event.id, payload_obj)

        queue = admin_event_stream.subscribe()
        yield _encode_sse(None, {"type": "worker_stream.connected"})

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    payload_obj = event.to_dict()
                    if is_worker_event_visible(
                        worker_user_id,
                        worker_id,
                        event.type,
                        payload_obj.get("payload", {}),
                    ):
                        yield _encode_sse(event.id, payload_obj)
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            admin_event_stream.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")
