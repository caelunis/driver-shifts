import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import psycopg
import pytest

from app.core import clock
from app.core.db import open_pool

BACKEND = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://shifts:shifts@127.0.0.1:5433/shifts_test"
)


def dbmate(url: str, *args: str) -> subprocess.CompletedProcess:
    """Run dbmate against `url` with the project's migrations."""
    return subprocess.run(
        ["dbmate", "--url", url.replace("postgresql://", "postgres://", 1) + "?sslmode=disable",
         "--migrations-dir", str(BACKEND / "db" / "migrations"), "--no-dump-schema", *args],
        capture_output=True, text=True,
    )


@pytest.fixture(scope="session")
def pool():
    """The test database, rebuilt from the migrations once per test run."""
    if shutil.which("dbmate") is None:
        pytest.skip("dbmate is not installed: brew install dbmate")
    try:
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True, connect_timeout=3) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
    except psycopg.OperationalError as e:
        pytest.skip(f"PostgreSQL is not reachable at {TEST_DATABASE_URL} ({e.__class__.__name__}). "
                    "Start it with: docker compose up -d db")
    result = dbmate(TEST_DATABASE_URL, "up")
    assert result.returncode == 0, result.stderr
    p = open_pool(TEST_DATABASE_URL, timeout=3)
    yield p
    p.close()


@pytest.fixture
def db(pool):
    """Empty tables for every test."""
    with pool.connection() as conn:
        conn.execute("TRUNCATE trips, shifts, sessions, drivers, users RESTART IDENTITY CASCADE")
    return pool


@pytest.fixture
def driver_id(db):
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
