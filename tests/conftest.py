import os

import pytest

from app.accounts import create_driver
from app.db import init_schema, open_pool
from app.storage import TripStorage

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://shifts:shifts@127.0.0.1:5433/shifts_test"
)


@pytest.fixture(scope="session")
def pool():
    try:
        p = open_pool(TEST_DATABASE_URL, timeout=3)
    except Exception as e:
        pytest.skip(
            f"PostgreSQL is not reachable at {TEST_DATABASE_URL} ({e.__class__.__name__}). "
            "Start it with: docker compose up -d db"
        )
    init_schema(p)
    yield p
    p.close()


@pytest.fixture
def db(pool):
    """Empty database for every test."""
    with pool.connection() as conn:
        conn.execute("TRUNCATE trips, sessions, drivers RESTART IDENTITY CASCADE")
    return pool


@pytest.fixture
def storage(db):
    return TripStorage(db)


@pytest.fixture
def driver_id(db):
    return create_driver(db, "driver@example.com", "password123", name="Test driver")
