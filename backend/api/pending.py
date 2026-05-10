"""Per-request future correlation map.

The gateway HTTP handler creates a future, drops it in the registry under
the request_id, then awaits it. A background Kafka consumer task watches
`transform-results` and fulfills the matching future.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PendingRegistry:
    def __init__(self) -> None:
        self._futures: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def register(self, request_id: str) -> asyncio.Future[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        async with self._lock:
            self._futures[request_id] = fut
        return fut

    async def resolve(self, request_id: str, payload: dict[str, Any]) -> bool:
        async with self._lock:
            fut = self._futures.pop(request_id, None)
        if fut is None:
            logger.debug("Result for unknown request_id=%s (already resolved/timed out)", request_id)
            return False
        if not fut.done():
            fut.set_result(payload)
            return True
        return False

    async def cancel(self, request_id: str) -> None:
        async with self._lock:
            fut = self._futures.pop(request_id, None)
        if fut and not fut.done():
            fut.cancel()
