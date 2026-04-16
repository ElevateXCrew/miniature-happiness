"""Realtime SSE stream for admin panel."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies.auth import require_role
from app.models.enums import UserRole
from app.services.event_stream import admin_event_stream

router = APIRouter(tags=["events"])


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
            payload = json.dumps(event.to_dict())
            yield f"id: {event.id}\ndata: {payload}\n\n"

        queue = admin_event_stream.subscribe()
        yield 'data: {"type": "admin_stream.connected"}\n\n'

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    payload = json.dumps(event.to_dict())
                    yield f"id: {event.id}\ndata: {payload}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            admin_event_stream.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")
