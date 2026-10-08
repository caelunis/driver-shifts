"""The read cache: hits, invalidation by writes, isolation between accounts, and what
happens when the database or Redis is down."""

from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

import app.api.response_cache as response_cache
import app.services.auth as auth_service
from app.main import create_app
from tests.api import code, sid
from tests.conftest import SETTINGS
from tests.factories import create_driver, day_shift

PASSWORD = "horse-battery-9"
DAY = {"work_date": "2026-10-01"}
TRIP = {
    "shift_id": sid(1),
    "started_at": "2026-10-01T08:10:00+05:00",
    "ended_at": "2026-10-01T08:32:00+05:00",
    "fare": 2400,
    "payment_method": "card",
    "commission_amount": 360,
}


def login(app, email="driver@example.com"):
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return c


@pytest.fixture
def app(db, driver_id):
    day_shift(db, driver_id)
    return create_app(db.database)


@pytest.fixture
def driver(app):
    return login(app)


# --- hits and invalidation ---


def test_a_repeated_read_comes_from_the_cache(driver):
    first = driver.get("/api/v1/summary", params=DAY)
    second = driver.get("/api/v1/summary", params=DAY)
    assert (first.headers["x-cache"], second.headers["x-cache"]) == ("miss", "hit")
    assert first.json() == second.json()


def test_a_write_invalidates_the_cached_read(driver):
    driver.get("/api/v1/summary", params=DAY)
    assert driver.post("/api/v1/trips", json=TRIP).status_code == 201
    after = driver.get("/api/v1/summary", params=DAY)
    assert after.headers["x-cache"] == "miss"
    assert after.json()["trips_count"] == 1


def test_a_failed_write_keeps_the_cache(driver):
    driver.get("/api/v1/summary", params=DAY)
    assert driver.post("/api/v1/trips", json={**TRIP, "fare": 0}).status_code == 422
    assert driver.get("/api/v1/summary", params=DAY).headers["x-cache"] == "hit"


def test_writes_reach_across_roles(app, db, driver, driver_id):
    create_driver(db, "admin@example.com", PASSWORD, role="admin")
    admin = login(app, "admin@example.com")
    admin.get("/api/v1/admin/drivers")
    admin.get(f"/api/v1/admin/drivers/{driver_id}/summary", params=DAY)

    driver.post("/api/v1/trips", json=TRIP)  # the driver's write…
    listing = admin.get("/api/v1/admin/drivers")  # …shows in the admin's totals
    assert listing.headers["x-cache"] == "miss" and listing.json()[0]["trips_count"] == 1
    assert admin.get(f"/api/v1/admin/drivers/{driver_id}/summary", params=DAY).json()["trips_count"] == 1

    driver.get("/api/v1/summary", params=DAY)
    trip_id = driver.get("/api/v1/trips", params=DAY).json()[0]["id"]
    admin.patch(f"/api/v1/admin/drivers/{driver_id}/trips/{trip_id}", json={"fare": 3000})  # the admin's…
    assert driver.get("/api/v1/summary", params=DAY).json()["revenue"] == 3000  # …in the driver's view


def test_cached_reads_are_per_account(app, db, driver):
    create_driver(db, "bob@example.com", PASSWORD, name="Bob")
    driver.get("/api/v1/me")
    bob = login(app, "bob@example.com")
    r = bob.get("/api/v1/me")
    assert r.headers["x-cache"] == "miss" and r.json()["email"] == "bob@example.com"


# --- the database is down ---


@pytest.fixture
def database_down(db, monkeypatch):
    """Call `down()` to make every new transaction fail as if PostgreSQL were gone. Cached
    copies count as no longer fresh, so the app has to try the database."""
    monkeypatch.setattr(response_cache, "CACHE_FRESH_TTL", timedelta(0))
    monkeypatch.setattr(auth_service, "SESSION_CACHE_TTL", timedelta(0))

    @asynccontextmanager
    async def unreachable():
        raise psycopg.OperationalError("connection refused")
        yield  # pragma: no cover

    return lambda: monkeypatch.setattr(db.database, "unit_of_work", unreachable)


def test_reads_fall_back_to_the_last_copy(driver, database_down):
    before = driver.get("/api/v1/summary", params=DAY)
    database_down()
    r = driver.get("/api/v1/summary", params=DAY)
    assert r.status_code == 200 and r.json() == before.json()
    assert r.headers["x-data-stale"] == "true"


def test_without_a_copy_or_for_writes_it_is_503(app, driver, database_down):
    database_down()
    for r in (
        driver.get("/api/v1/days"),  # never cached
        driver.post("/api/v1/shifts", json={}),
        TestClient(app).post(
            "/api/v1/auth/login", json={"email": "driver@example.com", "password": PASSWORD}
        ),
    ):
        assert r.status_code == 503 and code(r) == "db_unavailable"
        assert r.headers["retry-after"] == "30"


def test_an_unknown_session_cannot_be_checked_while_the_database_is_down(app, database_down):
    database_down()
    c = TestClient(app)
    c.cookies.set("session", "not-a-session-anyone-has")
    r = c.get("/api/v1/me")
    assert r.status_code == 503 and code(r) == "db_unavailable"


def test_a_password_change_ends_cached_sessions(app, db, driver, driver_id):
    create_driver(db, "admin@example.com", PASSWORD, role="admin")
    driver.get("/api/v1/me")  # the session is now in the cache
    login(app, "admin@example.com").patch(
        f"/api/v1/admin/drivers/{driver_id}", json={"password": "brand-new-pass-1"}
    )
    assert driver.get("/api/v1/me").status_code == 401


# --- Redis ---


def test_works_without_redis(db, driver_id, caplog):
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_timeout=0.2, socket_connect_timeout=0.2)
    app = create_app(db.database, redis=dead)
    c = login(app)
    assert c.get("/api/v1/me").headers["x-cache"] == "miss"
    assert c.get("/api/v1/me").headers["x-cache"] == "hit"  # from the in-process fallback
    assert "redis_unavailable" in caplog.text


def _test_redis_url() -> str | None:
    if SETTINGS is None or not SETTINGS.redis_url:
        return None
    parts = urlsplit(SETTINGS.redis_url)
    return urlunsplit(parts._replace(path="/15"))  # a database of its own, flushed below


@pytest.fixture
def redis(portal):
    url = _test_redis_url()
    if url is None:
        pytest.skip("REDIS_URL is not set")
    client = Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
    try:
        portal.call(client.flushdb)
    except Exception as e:
        pytest.skip(f"Redis is not reachable at {url} ({type(e).__name__})")
    yield client
    portal.call(client.flushdb)
    portal.call(client.aclose)


def test_redis_holds_the_cache_and_its_versions(db, driver_id, redis, portal):
    day_shift(db, driver_id)
    app = create_app(db.database, redis=redis)
    c = login(app)
    c.get("/api/v1/summary", params=DAY)
    assert c.get("/api/v1/summary", params=DAY).headers["x-cache"] == "hit"
    keys = portal.call(redis.keys, "resp:*")
    assert keys and all(k.startswith(b"resp:r") for k in keys)  # stored in Redis, not in memory
    assert c.post("/api/v1/trips", json=TRIP).status_code == 201
    assert portal.call(redis.get, f"ver:user:{driver_id}") == b"1"


def test_login_failures_count_across_app_instances(db, driver_id, redis):
    first, second = create_app(db.database, redis=redis), create_app(db.database, redis=redis)
    for instance in (first, second, first, second, first):
        TestClient(instance).post(
            "/api/v1/auth/login", json={"email": "driver@example.com", "password": "nope-123"}
        )
    r = TestClient(second).post(
        "/api/v1/auth/login", json={"email": "driver@example.com", "password": PASSWORD}
    )
    assert r.status_code == 429  # five failures, spread over two instances, still block


def test_redis_recovery_starts_a_new_epoch(db, redis, portal):
    app = create_app(db.database, redis=redis)
    cache = app.state.cache
    before = portal.call(cache.namespace, "ver:x")

    async def outage_then_recovery() -> None:
        async def fail() -> None:
            raise ConnectionError("down")

        async def fallback() -> None:
            return None

        guard = cache._guard
        await guard.run(fail, fallback)  # Redis "fails": later calls use memory for a while
        guard._down_until = 0  # the pause is over
        await cache.get("anything")  # first success after the outage

    portal.call(outage_then_recovery)
    after = portal.call(cache.namespace, "ver:x")
    assert before.startswith("r") and after.startswith("r") and after != before
