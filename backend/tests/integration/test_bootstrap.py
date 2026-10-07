import os
import subprocess
import sys

import psycopg
import pytest

from app.services import accounts
from scripts.seed_demo import DEMO_ADMIN, DEMO_DRIVERS, seed
from tests.conftest import BACKEND, TEST_DATABASE_URL
from tests.factories import create_driver

DEMO_EMAILS = {DEMO_ADMIN[0]: "admin", **{d.email: "driver" for d, _ in DEMO_DRIVERS}}


def roles(db):
    with db.connection() as conn:
        return {r["email"]: r["role"] for r in conn.execute("SELECT email, role FROM users")}


def run_script(module: str, *args: str, stdin: str = "", **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *args], input=stdin, capture_output=True, text=True,
        cwd=BACKEND, env={"PATH": os.environ["PATH"], "DATABASE_URL": TEST_DATABASE_URL, **env},
    )


def test_new_accounts_default_to_driver_role(db):
    create_driver(db, "d@example.com", "password123")
    assert roles(db) == {"d@example.com": "driver"}


def test_admin_has_no_driver_profile(db):
    admin = create_driver(db, "boss@example.com", "password123", role="admin")
    assert accounts.get_profile(db, admin).name is None
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM drivers").fetchone()["n"] == 0


def test_role_is_restricted(db):
    with pytest.raises(psycopg.errors.CheckViolation):
        create_driver(db, "x@example.com", "password123", role="superuser")


def test_ensure_admin_creates_once(db):
    assert accounts.ensure_admin(db, "Boss@Example.com", "password123") is True
    assert accounts.ensure_admin(db, "boss@example.com", "another-pass") is False
    assert roles(db) == {"boss@example.com": "admin"}


def test_ensure_admin_never_promotes_existing_driver(db):
    create_driver(db, "d@example.com", "password123")
    assert accounts.ensure_admin(db, "d@example.com", "password123") is False
    assert roles(db) == {"d@example.com": "driver"}


# --- demo data ---

def test_seed_on_empty_database(db):
    assert seed(db) is True
    assert roles(db) == DEMO_EMAILS
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"] == 5


def test_seed_is_skipped_when_accounts_exist(db):
    create_driver(db, "existing@example.com", "password123")
    assert seed(db) is False
    assert roles(db) == {"existing@example.com": "driver"}


def test_deleted_demo_account_does_not_come_back(db):
    seed(db)
    with db.connection() as conn:
        conn.execute("DELETE FROM users WHERE email = 'demo@example.com'")
    assert seed(db) is False  # e.g. on the next start
    assert "demo@example.com" not in roles(db)


# --- scripts ---

def test_bootstrap_script(db):
    r = run_script("scripts.bootstrap", SEED_DEMO="1",
                   ADMIN_EMAIL="owner@example.com", ADMIN_PASSWORD="owner-pass-1")
    assert r.returncode == 0, r.stderr
    assert roles(db) == {**DEMO_EMAILS, "owner@example.com": "admin"}
    again = run_script("scripts.bootstrap", SEED_DEMO="1")  # idempotent
    assert again.returncode == 0 and "skipped" in again.stdout


def test_create_admin_script(db):
    assert run_script("scripts.create_admin", "cli@example.com", stdin="short\n").returncode == 1
    ok = run_script("scripts.create_admin", "cli@example.com", stdin="long-enough-pass\n")
    assert ok.returncode == 0, ok.stderr
    assert run_script("scripts.create_admin", "cli@example.com", stdin="long-enough-pass\n").returncode == 1
    assert roles(db) == {"cli@example.com": "admin"}
