import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool

from .models import Profile
from .security import hash_password, verify_password

SESSION_TTL = timedelta(days=30)

# Verified against when the email is unknown, so a login attempt takes the same
# time whether or not the account exists (no account enumeration via timing).
_DUMMY_HASH = hash_password(secrets.token_hex(16))


class EmailTaken(Exception):
    pass


def _token_hash(token: str) -> str:
    # Only a hash of the session token is stored: a leaked sessions table
    # cannot be used to log in.
    return hashlib.sha256(token.encode()).hexdigest()


def create_driver(pool: ConnectionPool, email: str, password: str, name: str = "") -> int:
    try:
        with pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO drivers (email, password_hash, name) VALUES (%s, %s, %s) RETURNING id",
                (email.lower(), hash_password(password), name),
            ).fetchone()
    except UniqueViolation:
        raise EmailTaken(email)
    return row["id"]


def authenticate(pool: ConnectionPool, email: str, password: str) -> int | None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM drivers WHERE lower(email) = lower(%s)", (email,)
        ).fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return row["id"] if verify_password(password, row["password_hash"]) else None


def create_session(pool: ConnectionPool, driver_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, driver_id, expires_at) VALUES (%s, %s, %s)",
            (_token_hash(token), driver_id, datetime.now(timezone.utc) + SESSION_TTL),
        )
    return token


def driver_by_session(pool: ConnectionPool, token: str) -> int | None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT driver_id, expires_at > now() AS alive FROM sessions WHERE token_hash = %s",
            (_token_hash(token),),
        ).fetchone()
        if row and not row["alive"]:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))
            return None
    return row["driver_id"] if row else None


def delete_session(pool: ConnectionPool, token: str) -> None:
    with pool.connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))


_PROFILE_COLUMNS = "id, email, name, car, default_tz, default_commission_pct"


def get_profile(pool: ConnectionPool, driver_id: int) -> Profile:
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT {_PROFILE_COLUMNS} FROM drivers WHERE id = %s", (driver_id,)
        ).fetchone()
    return Profile(**row)


# Columns a driver may change through PATCH /api/me (also guards the dynamic SQL below)
_EDITABLE = ("name", "car", "default_tz", "default_commission_pct")


def update_profile(pool: ConnectionPool, driver_id: int, changes: dict) -> Profile:
    changes = {k: v for k, v in changes.items() if k in _EDITABLE}
    if changes:
        assignments = ", ".join(f"{k} = %s" for k in changes)
        with pool.connection() as conn:
            conn.execute(
                f"UPDATE drivers SET {assignments} WHERE id = %s", (*changes.values(), driver_id)
            )
    return get_profile(pool, driver_id)
