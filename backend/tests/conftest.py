import functools
import inspect
import os
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from anyio.from_thread import BlockingPortal, start_blocking_portal
from fastapi.testclient import TestClient
from psycopg.rows import DictRow, dict_row
from pydantic import ValidationError

from app.core import clock
from app.core.config import Settings, get_settings
from app.db.database import Database

BACKEND = Path(__file__).resolve().parent.parent


def _settings() -> Settings | None:
    try:
        return get_settings()
    except ValidationError:
        return None


# The same POSTGRES_* settings as the app (environment or .env), with the test database
SETTINGS = _settings()
TEST_DATABASE_URL = SETTINGS.database_url(SETTINGS.postgres_test_db) if SETTINGS else ""


def db_env(**extra: str) -> dict[str, str]:
    """Environment for a subprocess that should use the test database."""
    assert SETTINGS is not None
    return {
        "PATH": os.environ["PATH"],
        "POSTGRES_HOST": SETTINGS.postgres_host,
        "POSTGRES_PORT": str(SETTINGS.postgres_port),
        "POSTGRES_USER": SETTINGS.postgres_user,
        "POSTGRES_PASSWORD": SETTINGS.postgres_password.get_secret_value(),
        "POSTGRES_DB": SETTINGS.postgres_test_db,
        # Explicit, so values from a developer's .env cannot leak into the test
        "SEED_DEMO": "0",
        "ADMIN_EMAIL": "",
        "ADMIN_PASSWORD": "",
        **extra,
    }


def dbmate(url: str, *args: str) -> subprocess.CompletedProcess:
    """Run dbmate against `url` with the project's migrations."""
    return subprocess.run(
        [
            "dbmate",
            "--url",
            url.replace("postgresql://", "postgres://", 1) + "?sslmode=disable",
            "--migrations-dir",
            str(BACKEND / "db" / "migrations"),
            "--no-dump-schema",
            *args,
        ],
        capture_output=True,
        text=True,
    )


class SyncService:
    """A service whose coroutine methods tests call like plain functions: each call runs
    on the shared event loop (the one the app under test uses) and waits for the result.
    Calls from several threads run concurrently on that loop."""

    def __init__(self, target: Any, portal: BlockingPortal) -> None:
        self._target, self._portal = target, portal

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if not inspect.iscoroutinefunction(attr):
            return attr
        return lambda *args, **kwargs: self._portal.call(functools.partial(attr, *args, **kwargs))


class TestDb:
    """The test database: the app's async Database plus sync helpers for tests."""

    __test__ = False  # not a test class, despite the name

    def __init__(self, database: Database, portal: BlockingPortal) -> None:
        self.database, self.portal = database, portal

    def service(self, cls: type) -> Any:
        """e.g. db.service(ShiftService).start(driver_id)"""
        return SyncService(cls(self.database), self.portal)

    def run(self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        """Run a coroutine function on the shared loop, e.g. with a unit of work."""
        return self.portal.call(functools.partial(fn, *args, **kwargs))

    def connection(self) -> psycopg.Connection[DictRow]:
        """A plain sync connection for raw SQL in tests (committed when the block ends)."""
        return psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row)


@pytest.fixture(scope="session")
def portal() -> Iterator[BlockingPortal]:
    """One event loop for the whole run, in a background thread. The async connection
    pool lives on it, and every TestClient sends its requests through it: asyncio
    objects such as pool connections must stay on the loop that created them."""
    with start_blocking_portal() as p:
        TestClient.portal = p  # instances without a portal of their own use this one
        try:
            yield p
        finally:
            TestClient.portal = None


@pytest.fixture(scope="session")
def database(portal: BlockingPortal) -> Iterator[Database]:
    """The test database, rebuilt from the migrations once per test run."""
    if shutil.which("dbmate") is None:
        pytest.skip("dbmate is not installed: brew install dbmate")
    if SETTINGS is None:
        pytest.skip("POSTGRES_* settings are missing: cp .env.example .env")
    try:
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True, connect_timeout=3) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
    except psycopg.OperationalError as e:
        pytest.skip(
            f"PostgreSQL is not reachable at {SETTINGS.postgres_host}:{SETTINGS.postgres_port}"
            f" ({e.__class__.__name__}). "
            "Start it with: docker compose up -d db"
        )
    result = dbmate(TEST_DATABASE_URL, "up")
    assert result.returncode == 0, result.stderr
    database = portal.call(Database.connect, TEST_DATABASE_URL, 3)
    yield database
    portal.call(database.close)


@pytest.fixture
def db(database: Database, portal: BlockingPortal) -> TestDb:
    """Empty tables for every test."""
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("TRUNCATE trips, shifts, sessions, drivers, users RESTART IDENTITY CASCADE")
    return TestDb(database, portal)


@pytest.fixture(autouse=True)
def shift_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shifts get ids sid(1), sid(2), … in the order a test creates them (the app's
    UUIDv7 otherwise), so tests can name a shift without carrying its id around."""
    from uuid import UUID

    from tests.api import sid

    counter = iter(range(1, 1_000_000))
    monkeypatch.setattr("app.repositories.shifts.uuid7", lambda: UUID(sid(next(counter))))


@pytest.fixture
def driver_id(db: TestDb) -> str:
    from tests.factories import create_driver

    return create_driver(db, "driver@example.com", "horse-battery-9", name="Test driver")


# Tests use dates around the start of October 2026; "now" is pinned right after them,
# so rules like "not in the future" and "at most 7 days back" give the same answer
# whenever the tests run.
NOW = datetime.fromisoformat("2026-10-03T12:00:00+05:00")


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return NOW
