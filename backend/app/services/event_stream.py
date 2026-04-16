"""
In-process event stream for admin sync (SSE-backed).
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import count
from typing import Any


@dataclass(slots=True)
class AdminEvent:
    id: int
    type: str
    timestamp: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class AdminEventStream:
    def __init__(self, history_size: int = 300) -> None:
        self._subscribers: set[asyncio.Queue[AdminEvent]] = set()
        self._history: deque[AdminEvent] = deque(maxlen=history_size)
        self._ids = count(1)

    def publish(self, event_type: str, payload: dict[str, Any]) -> AdminEvent:
        event = AdminEvent(
            id=next(self._ids),
            type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            payload=payload,
        )
        self._history.append(event)
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)
        return event

    def subscribe(self) -> asyncio.Queue[AdminEvent]:
        queue: asyncio.Queue[AdminEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[AdminEvent]) -> None:
        self._subscribers.discard(queue)

    def history_since(self, since_id: int | None) -> list[AdminEvent]:
        if since_id is None:
            return list(self._history)
        return [event for event in self._history if event.id > since_id]


admin_event_stream = AdminEventStream()
