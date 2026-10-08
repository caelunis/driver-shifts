"""Counting events in a sliding time window: request throttling and failed logins.

The counters live behind RateLimitStore. MemoryRateLimitStore keeps them in the
process, which is right for a single instance; a shared store (Redis) plugs in
behind the same interface for several instances.
"""

import time
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from app.core.constants import LOGIN_FAILURE_WINDOW, LOGIN_MAX_FAILURES

# Keys with no event inside their window are dropped once the store grows past this
_PRUNE_ABOVE = 10_000


@dataclass(frozen=True, slots=True)
class WindowCount:
    count: int  # events inside the window, including the one just recorded
    retry_after: int  # whole seconds until the oldest of them leaves the window


class RateLimitStore(Protocol):
    async def hit(self, key: str, window: timedelta) -> WindowCount:
        """Record an event now and count the events of `key` inside `window`."""
        ...

    async def peek(self, key: str, window: timedelta) -> WindowCount:
        """Count without recording."""
        ...

    async def clear(self, key: str) -> None: ...


class MemoryRateLimitStore:
    """A log of timestamps per key. The event loop is single-threaded and nothing
    here awaits, so every method runs to completion without interleaving."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}

    def _window(self, key: str, window: timedelta, now: float) -> deque[float]:
        events = self._events.setdefault(key, deque())
        horizon = now - window.total_seconds()
        while events and events[0] <= horizon:
            events.popleft()
        return events

    def _count(self, events: deque[float], window: timedelta, now: float) -> WindowCount:
        if not events:
            return WindowCount(0, 0)
        return WindowCount(len(events), max(1, int(events[0] + window.total_seconds() - now) + 1))

    async def hit(self, key: str, window: timedelta) -> WindowCount:
        now = time.monotonic()
        events = self._window(key, window, now)
        events.append(now)
        if len(self._events) > _PRUNE_ABOVE:
            self._prune(window, now)
        return self._count(events, window, now)

    async def peek(self, key: str, window: timedelta) -> WindowCount:
        now = time.monotonic()
        result = self._count(self._window(key, window, now), window, now)
        if result.count == 0:
            self._events.pop(key, None)
        return result

    async def clear(self, key: str) -> None:
        self._events.pop(key, None)

    def _prune(self, window: timedelta, now: float) -> None:
        horizon = now - window.total_seconds()
        for key in [k for k, ev in self._events.items() if not ev or ev[-1] <= horizon]:
            del self._events[key]


class LoginLimiter:
    """Blocks an email after too many failed logins within a time window."""

    def __init__(
        self,
        store: RateLimitStore,
        max_failures: int = LOGIN_MAX_FAILURES,
        window: timedelta = LOGIN_FAILURE_WINDOW,
    ) -> None:
        self._store, self._max, self._window = store, max_failures, window

    @staticmethod
    def _key(email: str) -> str:
        return f"login-failures:{email.lower()}"

    async def retry_after(self, email: str) -> int:
        """Seconds until the next attempt is allowed; 0 if not blocked."""
        state = await self._store.peek(self._key(email), self._window)
        return state.retry_after if state.count >= self._max else 0

    async def failure(self, email: str) -> None:
        await self._store.hit(self._key(email), self._window)

    async def success(self, email: str) -> None:
        await self._store.clear(self._key(email))
