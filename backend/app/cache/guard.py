"""Redis with a fallback: when Redis fails, the in-process stores take over for a while."""

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TypeVar

from redis.exceptions import RedisError

from app.core.constants import REDIS_RETRY_AFTER

log = logging.getLogger(__name__)

T = TypeVar("T")


class RedisGuard:
    """Runs Redis calls and switches to the fallback when Redis fails.

    After a failure Redis is left alone for `retry_after`, so a dead Redis costs one
    timeout per period instead of one per request. The first success after an outage
    runs the `on_recovery` callbacks (the cache uses it to drop what may have gone stale).
    """

    def __init__(self, enabled: bool, retry_after: timedelta = REDIS_RETRY_AFTER) -> None:
        self.enabled = enabled
        self._retry_after = retry_after.total_seconds()
        self._down_until = 0.0
        self._was_down = False
        self._on_recovery: list[Callable[[], Awaitable[None]]] = []

    def on_recovery(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._on_recovery.append(callback)

    @property
    def available(self) -> bool:
        return self.enabled and time.monotonic() >= self._down_until

    async def run(self, redis_call: Callable[[], Awaitable[T]], fallback: Callable[[], Awaitable[T]]) -> T:
        if not self.available:
            return await fallback()
        try:
            result = await redis_call()
        except (RedisError, OSError) as e:
            if not self._was_down:
                log.warning("redis_unavailable", extra={"error": type(e).__name__})
            self._was_down = True
            self._down_until = time.monotonic() + self._retry_after
            return await fallback()
        if self._was_down:
            self._was_down = False
            log.info("redis_recovered")
            for callback in self._on_recovery:
                await callback()
        return result
