import asyncio
from datetime import timedelta

import pytest

import app.core.ratelimit as ratelimit
from app.core.ratelimit import LoginLimiter, MemoryRateLimitStore

WINDOW = timedelta(seconds=60)


@pytest.fixture
def clock(monkeypatch):
    """A controllable monotonic clock."""
    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    return now


def run(coro):
    return asyncio.run(coro)


def test_counts_inside_the_window_only(clock):
    store = MemoryRateLimitStore()
    assert run(store.hit("k", WINDOW)).count == 1
    clock[0] += 30
    assert run(store.hit("k", WINDOW)).count == 2
    clock[0] += 31  # the first event is now 61 s old
    assert run(store.peek("k", WINDOW)).count == 1


def test_retry_after_is_when_the_oldest_event_leaves(clock):
    store = MemoryRateLimitStore()
    run(store.hit("k", WINDOW))
    clock[0] += 20
    assert run(store.hit("k", WINDOW)).retry_after == 41  # 60 - 20, rounded up


def test_clear_and_peek_do_not_record(clock):
    store = MemoryRateLimitStore()
    assert run(store.peek("k", WINDOW)).count == 0
    run(store.hit("k", WINDOW))
    run(store.clear("k"))
    assert run(store.peek("k", WINDOW)).count == 0


def test_login_limiter_blocks_after_failures_and_forgets_on_success(clock):
    limiter = LoginLimiter(MemoryRateLimitStore(), max_failures=2, window=WINDOW)
    for _ in range(2):
        assert run(limiter.retry_after("A@x.kz")) == 0
        run(limiter.failure("a@x.kz"))
    assert run(limiter.retry_after("a@X.kz")) > 0  # case does not matter
    run(limiter.success("a@x.kz"))
    assert run(limiter.retry_after("a@x.kz")) == 0


def test_old_keys_are_pruned(clock, monkeypatch):
    monkeypatch.setattr(ratelimit, "_PRUNE_ABOVE", 3)
    store = MemoryRateLimitStore()
    for k in "abcd":
        run(store.hit(k, WINDOW))
    clock[0] += 120
    run(store.hit("e", WINDOW))
    assert set(store._events) == {"e"}
