"""Migrations apply on an empty database, roll back completely, and apply again."""

import psycopg
import pytest

from tests.conftest import TEST_DATABASE_URL, dbmate

SCRATCH_DB = "shifts_migrations_test"
SCRATCH_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/" + SCRATCH_DB


@pytest.fixture
def scratch_db(database):  # `database` makes sure Postgres and dbmate are available
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


def rollback(url: str, steps: int) -> None:
    for _ in range(steps):
        result = dbmate(url, "rollback")
        assert result.returncode == 0, result.stderr


def up(url: str) -> None:
    result = dbmate(url, "up")
    assert result.returncode == 0, result.stderr


def test_stricter_data_migration_converts_profiles(scratch_db):
    up(scratch_db)
    rollback(scratch_db, 2)  # before 004: free-text car and fixed offsets
    with psycopg.connect(scratch_db) as conn:
        for i, (car, tz) in enumerate(
            [
                ("Hyundai Accent, 777 AAA 02", "+05:00"),
                ("Kia Rio 777AAA02", "+06:00"),  # same plate typed twice: the first keeps it
                ("Toyota Camry", "+05:45"),
                ("", "-03:00"),
            ],
            start=1,
        ):
            conn.execute(
                "INSERT INTO users (id, email, password_hash, role, created_at)"
                " VALUES (%s, %s, 'x', 'driver', now() + %s * interval '1 second')",
                (i, f"d{i}@example.com", i),
            )
            conn.execute(
                "INSERT INTO drivers (user_id, name, car, default_tz) VALUES (%s, 'D', %s, %s)", (i, car, tz)
            )

    up(scratch_db)
    with psycopg.connect(scratch_db) as conn:
        rows = conn.execute(
            "SELECT d.car_model, d.car_plate, d.timezone FROM drivers d JOIN users u ON u.id = d.user_id"
            " ORDER BY u.email"
        ).fetchall()
    assert rows == [
        ("Hyundai Accent", "777AAA02", "Asia/Almaty"),
        ("Kia Rio 777AAA02", None, "Etc/GMT-6"),
        ("Toyota Camry", None, "Asia/Kathmandu"),
        ("", None, "Etc/GMT+3"),
    ]

    rollback(scratch_db, 2)
    with psycopg.connect(scratch_db) as conn:
        rows = conn.execute(
            "SELECT d.car, d.default_tz FROM drivers d JOIN users u ON u.id = d.user_id ORDER BY u.email"
        ).fetchall()
    assert rows == [
        ("Hyundai Accent, 777AAA02", "+05:00"),
        ("Kia Rio 777AAA02", "+06:00"),
        ("Toyota Camry", "+05:45"),
        ("", "-03:00"),
    ]


def test_uuid_migration_carries_every_relation_over(scratch_db):
    up(scratch_db)
    rollback(scratch_db, 1)  # before 005: integer keys, text trip ids
    uuid_trip = "0192f0a0-0000-7000-8000-000000000001"
    with psycopg.connect(scratch_db) as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, created_at) VALUES"
            " (1, 'a@x.kz', 'h', 'admin', now() - interval '2 days'),"
            " (2, 'd@x.kz', 'h', 'driver', now() - interval '1 day')"
        )
        conn.execute("INSERT INTO drivers (user_id, name) VALUES (2, 'D')")
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at)"
            " VALUES ('tok', 2, now() + interval '1 day')"
        )
        conn.execute(
            "INSERT INTO shifts (id, driver_id, started_at, ended_at, start_offset_min, end_offset_min,"
            " local_day)"
            " VALUES (7, 2, '2026-10-01 08:00+05', '2026-10-01 12:00+05', 300, 300, '2026-10-01')"
        )
        conn.execute(
            "INSERT INTO trips (driver_id, id, shift_id, start_at, end_at, start_offset_min, end_offset_min,"
            " amount, payment, commission) VALUES"
            " (2, 't1', 7, '2026-10-01 08:10+05', '2026-10-01 08:30+05', 300, 300, 1000, 'cash', 100),"
            " (2, %s, 7, '2026-10-01 09:00+05', '2026-10-01 09:30+05', 300, 300, 2000, 'card', 200)",
            (uuid_trip,),
        )

    up(scratch_db)
    with psycopg.connect(scratch_db) as conn:
        trips = conn.execute(
            "SELECT t.id::text, t.fare, t.payment_method, d.full_name, s.work_date::text"
            " FROM trips t JOIN shifts s ON s.id = t.shift_id AND s.driver_id = t.driver_id"
            " JOIN drivers d ON d.user_id = t.driver_id ORDER BY t.started_at"
        ).fetchall()
        sessions = conn.execute("SELECT u.email FROM sessions s JOIN users u ON u.id = s.user_id").fetchall()
    assert [row[1:] for row in trips] == [
        (1000, "cash", "D", "2026-10-01"),
        (2000, "card", "D", "2026-10-01"),
    ]
    assert trips[1][0] == uuid_trip  # a UUID id is kept as it is
    assert len(trips[0][0]) == 36  # "t1" got a stable UUID of its own
    assert sessions == [("d@x.kz",)]

    rollback(scratch_db, 1)
    with psycopg.connect(scratch_db) as conn:
        users = conn.execute("SELECT id, email FROM users ORDER BY id").fetchall()
        trips = conn.execute("SELECT driver_id, shift_id, amount FROM trips ORDER BY start_at").fetchall()
        next_id = conn.execute("SELECT nextval('users_id_seq')").fetchone()[0]
    assert users == [(1, "a@x.kz"), (2, "d@x.kz")]  # renumbered in creation order
    assert trips == [(2, 1, 1000), (2, 1, 2000)]
    assert next_id == 3
