"""
Realtime SSE stream for admin panel.
Phase 1 stub — full implementation in Phase 3.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["events"])


@router.get("/events/admin/stream")
async def admin_event_stream() -> StreamingResponse:
    async def generator():
        yield 'data: {"type": "connected"}\n\n'

    return StreamingResponse(generator(), media_type="text/event-stream")
