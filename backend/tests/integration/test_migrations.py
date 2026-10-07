"""Migrations apply on an empty database, roll back completely, and apply again."""
import psycopg
import pytest

from tests.conftest import TEST_DATABASE_URL, dbmate

SCRATCH_DB = "shifts_migrations_test"
SCRATCH_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/" + SCRATCH_DB


@pytest.fixture
def scratch_db(pool):  # `pool` makes sure Postgres and dbmate are available
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
        conn.execute(f"CREATE DATABASE {SCRATCH_DB}")
    yield SCRATCH_URL
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")


def tables(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    return {r[0] for r in rows} - {"schema_migrations"}


def applied(url: str) -> int:
    with psycopg.connect(url) as conn:
        return conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]


def test_up_down_up(scratch_db):
    up = dbmate(scratch_db, "up")
    assert up.returncode == 0, up.stderr
    expected = {"users", "drivers", "sessions", "shifts", "trips"}
    assert tables(scratch_db) == expected
    count = applied(scratch_db)

    for _ in range(count):  # roll back every migration, one by one
        down = dbmate(scratch_db, "rollback")
        assert down.returncode == 0, down.stderr
    assert tables(scratch_db) == set()
    assert applied(scratch_db) == 0

    again = dbmate(scratch_db, "up")
    assert again.returncode == 0, again.stderr
    assert tables(scratch_db) == expected


def test_every_migration_has_a_down_section():
    from tests.conftest import BACKEND
    for path in sorted((BACKEND / "db" / "migrations").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        assert "-- migrate:up" in text and "-- migrate:down" in text, path.name
        down = text.split("-- migrate:down", 1)[1].strip()
        assert down, f"{path.name}: empty migrate:down"
