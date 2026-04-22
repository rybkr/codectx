from __future__ import annotations

import asyncio
from typing import Any

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextEvent:
    kind: str
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[ContextEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: ContextEvent) -> None:
        async with self._lock:
            for queue in list(self._subscribers):
                await queue.put(event)

    async def subscribe(self) -> asyncio.Queue[ContextEvent]:
        queue: asyncio.Queue[ContextEvent] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[ContextEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)
