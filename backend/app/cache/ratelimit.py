"""Rate-limit counters in Redis, shared by every app instance, with the in-process store
as the fallback."""

import time
import uuid
from datetime import timedelta

from redis.asyncio import Redis

from app.cache.guard import RedisGuard
from app.core.ratelimit import MemoryRateLimitStore, WindowCount


class RedisRateLimitStore:
    """A sliding window per key: a sorted set of event timestamps (wall clock, since
    several machines share it)."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def _count(self, key: str, window: timedelta, record: bool) -> WindowCount:
        now = time.time()
        span = window.total_seconds()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, now - span)
            if record:
                pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
                pipe.pexpire(key, int(span * 1000))
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            *_, count, oldest = await pipe.execute()
        if not count:
            return WindowCount(0, 0)
        return WindowCount(int(count), max(1, int(oldest[0][1] + span - now) + 1))

    async def hit(self, key: str, window: timedelta) -> WindowCount:
        return await self._count(key, window, record=True)

    async def peek(self, key: str, window: timedelta) -> WindowCount:
        return await self._count(key, window, record=False)

    async def clear(self, key: str) -> None:
        await self._redis.delete(key)


class ResilientRateLimitStore:
    """Redis when it is up; counters in this process otherwise."""

    def __init__(self, redis: Redis | None, guard: RedisGuard) -> None:
        self._redis = RedisRateLimitStore(redis) if redis is not None else None
        self._memory = MemoryRateLimitStore()
        self._guard = guard

    def _r(self) -> RedisRateLimitStore:
        assert self._redis is not None  # noqa: S101 - the guard calls Redis only when enabled
        return self._redis

    async def hit(self, key: str, window: timedelta) -> WindowCount:
        return await self._guard.run(
            lambda: self._r().hit(key, window), lambda: self._memory.hit(key, window)
        )

    async def peek(self, key: str, window: timedelta) -> WindowCount:
        return await self._guard.run(
            lambda: self._r().peek(key, window), lambda: self._memory.peek(key, window)
        )

    async def clear(self, key: str) -> None:
        await self._memory.clear(key)
        await self._guard.run(lambda: self._r().clear(key), lambda: self._memory.clear(key))
