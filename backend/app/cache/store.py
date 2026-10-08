"""The cache: Redis, with an in-process copy that takes over when Redis is down."""

import time
from collections import OrderedDict
from datetime import timedelta

from redis.asyncio import Redis

from app.cache.guard import RedisGuard
from app.core.constants import CACHE_MEMORY_MAX_ENTRIES, CACHE_MEMORY_TTL_CAP

EPOCH_KEY = "cache:epoch"


class MemoryStore:
    """Bounded and short-lived: least recently used entries go first, and nothing is kept
    longer than `ttl_cap` (each app instance has its own copy)."""

    def __init__(
        self, ttl_cap: timedelta = CACHE_MEMORY_TTL_CAP, max_entries: int = CACHE_MEMORY_MAX_ENTRIES
    ) -> None:
        self._ttl_cap = ttl_cap.total_seconds()
        self._max = max_entries
        self._values: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._counters: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        item = self._values.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= time.monotonic():
            del self._values[key]
            return None
        self._values.move_to_end(key)
        return value

    async def set(self, key: str, value: bytes, ttl: timedelta) -> None:
        self._values[key] = (time.monotonic() + min(ttl.total_seconds(), self._ttl_cap), value)
        self._values.move_to_end(key)
        while len(self._values) > self._max:
            self._values.popitem(last=False)

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)

    async def incr(self, key: str) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    async def get_ints(self, *keys: str) -> list[int]:
        return [self._counters.get(k, 0) for k in keys]


class Cache:
    """Values with a TTL plus version counters, in Redis when it is up.

    Every value is also written to the in-process store, so recent entries survive a
    Redis outage. Versions written meanwhile exist only in this process; so when Redis
    comes back the epoch goes up, and every key built before (keys include the epoch,
    see namespace()) stops matching anything stale.
    """

    def __init__(self, redis: Redis | None, guard: RedisGuard, memory: MemoryStore | None = None) -> None:
        self._redis = redis
        self._guard = guard
        self._memory = memory or MemoryStore()
        guard.on_recovery(self._new_epoch)

    @classmethod
    def in_process(cls) -> "Cache":
        """No Redis: for scripts and tests, and for an app run without REDIS_URL."""
        return cls(None, RedisGuard(enabled=False))

    async def _new_epoch(self) -> None:
        assert self._redis is not None  # noqa: S101 - recovery happens only with Redis
        await self._redis.incr(EPOCH_KEY)

    def _r(self) -> Redis:
        assert self._redis is not None  # noqa: S101 - the guard calls Redis only when enabled
        return self._redis

    async def get(self, key: str) -> bytes | None:
        async def from_redis() -> bytes | None:
            value = await self._r().get(key)
            return value.encode() if isinstance(value, str) else value

        return await self._guard.run(from_redis, lambda: self._memory.get(key))

    async def set(self, key: str, value: bytes, ttl: timedelta) -> None:
        await self._memory.set(key, value, ttl)

        async def to_redis() -> None:
            await self._r().set(key, value, px=int(ttl.total_seconds() * 1000))

        async def nothing() -> None:
            return None

        await self._guard.run(to_redis, nothing)

    async def delete(self, key: str) -> None:
        await self._memory.delete(key)

        async def from_redis() -> None:
            await self._r().delete(key)

        async def nothing() -> None:
            return None

        await self._guard.run(from_redis, nothing)

    async def bump(self, *keys: str) -> None:
        """Increment version counters: everything cached under the old versions is gone."""

        async def in_redis() -> None:
            async with self._r().pipeline(transaction=False) as pipe:
                for k in keys:
                    pipe.incr(k)
                await pipe.execute()

        async def in_memory() -> None:
            for k in keys:
                await self._memory.incr(k)

        await self._guard.run(in_redis, in_memory)

    async def namespace(self, *version_keys: str) -> str:
        """The epoch and the given versions as one key fragment, read in one round trip.
        Fragments from Redis and from memory never coincide ("r…" / "m…")."""

        async def from_redis() -> str:
            values = await self._r().mget([EPOCH_KEY, *version_keys])
            return "r" + ".".join(str(int(v or 0)) for v in values)

        async def from_memory() -> str:
            return "m" + ".".join(str(v) for v in await self._memory.get_ints(*version_keys))

        return await self._guard.run(from_redis, from_memory)
