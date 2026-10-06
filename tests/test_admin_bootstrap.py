import subprocess
import sys

from app.accounts import create_driver
from app.db import init_schema
from app.main import DEMO_TRIPS
from app.seed import DEMO_ADMIN_EMAIL, DEMO_EMAIL, ensure_admin, seed_demo
from tests.conftest import TEST_DATABASE_URL


def roles(db):
    with db.connection() as conn:
        return {r["email"]: r["role"] for r in conn.execute("SELECT email, role FROM drivers")}


def test_new_accounts_default_to_driver_role(db):
    create_driver(db, "d@example.com", "password123")
    assert roles(db) == {"d@example.com": "driver"}


def test_ensure_admin_creates_once(db):
    assert ensure_admin(db, "Boss@Example.com", "password123") is True
    assert ensure_admin(db, "boss@example.com", "another-pass") is False
    assert roles(db) == {"boss@example.com": "admin"}


def test_ensure_admin_never_promotes_existing_driver(db):
    create_driver(db, "d@example.com", "password123")
    assert ensure_admin(db, "d@example.com", "password123") is False
    assert roles(db) == {"d@example.com": "driver"}


def test_seed_demo_on_empty_database(db):
    seed_demo(db, DEMO_TRIPS)
    assert roles(db) == {DEMO_EMAIL: "driver", DEMO_ADMIN_EMAIL: "admin"}


def test_seed_demo_adds_admin_to_existing_database_without_reseeding_driver(db):
    create_driver(db, "existing@example.com", "password123")
    seed_demo(db, DEMO_TRIPS)
    assert roles(db) == {"existing@example.com": "driver", DEMO_ADMIN_EMAIL: "admin"}


def test_deleted_demo_driver_does_not_come_back(db):
    seed_demo(db, DEMO_TRIPS)
    with db.connection() as conn:
        conn.execute("DELETE FROM drivers WHERE email = %s", (DEMO_EMAIL,))
    seed_demo(db, DEMO_TRIPS)  # e.g. after a restart
    assert roles(db) == {DEMO_ADMIN_EMAIL: "admin"}


def test_role_column_is_added_to_old_databases(db):
    create_driver(db, "old@example.com", "password123")
    with db.connection() as conn:
        conn.execute("ALTER TABLE drivers DROP COLUMN role")  # schema before admins existed
    init_schema(db)
    assert roles(db) == {"old@example.com": "driver"}


def test_role_is_restricted(db):
    import psycopg
    import pytest
    with pytest.raises(psycopg.errors.CheckViolation):
        create_driver(db, "x@example.com", "password123", role="superuser")


def test_create_admin_cli(db):
    run = lambda *args, pw: subprocess.run(
        [sys.executable, "-m", "app.create_admin", *args], input=pw + "\n",
        capture_output=True, text=True, env={"DATABASE_URL": TEST_DATABASE_URL, "PATH": ""},
    )
    assert run("cli@example.com", "--name", "Иван", pw="short").returncode == 1
    ok = run("cli@example.com", "--name", "Иван", pw="long-enough-pass")
    assert ok.returncode == 0, ok.stderr
    assert run("cli@example.com", pw="long-enough-pass").returncode == 1  # already exists
    assert roles(db) == {"cli@example.com": "admin"}
