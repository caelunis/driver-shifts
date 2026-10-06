import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from psycopg.errors import UniqueViolation
from psycopg_pool import ConnectionPool

from .models import DriverInfo, Profile
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


def create_driver(pool: ConnectionPool, email: str, password: str, name: str = "",
                  role: str = "driver") -> int:
    try:
        with pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO drivers (email, password_hash, name, role) VALUES (%s, %s, %s, %s)"
                " RETURNING id",
                (email.lower(), hash_password(password), name, role),
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


def delete_driver(pool: ConnectionPool, driver_id: int) -> bool:
    """Delete a driver account (never an admin); trips and sessions go via ON DELETE CASCADE."""
    with pool.connection() as conn:
        deleted = conn.execute(
            "DELETE FROM drivers WHERE id = %s AND role = 'driver' RETURNING id", (driver_id,)
        ).fetchone()
    return deleted is not None


def create_session(pool: ConnectionPool, driver_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, driver_id, expires_at) VALUES (%s, %s, %s)",
            (_token_hash(token), driver_id, datetime.now(timezone.utc) + SESSION_TTL),
        )
    return token


def account_by_session(pool: ConnectionPool, token: str) -> dict | None:
    """{"id", "role"} for a live session, None for unknown or expired tokens."""
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT d.id, d.role, s.expires_at > now() AS alive"
            " FROM sessions s JOIN drivers d ON d.id = s.driver_id WHERE s.token_hash = %s",
            (_token_hash(token),),
        ).fetchone()
        if row and not row["alive"]:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))
            return None
    return {"id": row["id"], "role": row["role"]} if row else None


def delete_session(pool: ConnectionPool, token: str) -> None:
    with pool.connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))


_PROFILE_COLUMNS = "id, email, role, name, car, default_tz, default_commission_pct"


def get_profile(pool: ConnectionPool, driver_id: int) -> Profile:
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT {_PROFILE_COLUMNS} FROM drivers WHERE id = %s", (driver_id,)
        ).fetchone()
    return Profile(**row)


def set_timezone(pool: ConnectionPool, driver_id: int, tz: str) -> Profile:
    with pool.connection() as conn:
        conn.execute("UPDATE drivers SET default_tz = %s WHERE id = %s", (tz, driver_id))
    return get_profile(pool, driver_id)


# --- admin: drivers with totals ---

_DRIVER_INFO_SQL = """
    SELECT d.id, d.email, d.role, d.name, d.car, d.default_tz, d.default_commission_pct,
           d.created_at, count(t.id) AS trips_count,
           coalesce(sum(t.amount), 0) AS revenue,
           coalesce(sum(t.amount - t.commission), 0) AS net,
           max(t.local_day) AS last_trip_day
    FROM drivers d LEFT JOIN trips t ON t.driver_id = d.id
    WHERE d.role = 'driver' {filter}
    GROUP BY d.id
    ORDER BY lower(d.name), d.id
"""


def _like(q: str) -> str:
    """Substring pattern for ILIKE with the user's % and _ taken literally."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_drivers(pool: ConnectionPool, q: str | None = None) -> list[DriverInfo]:
    """Drivers only (admins are not listed), optionally filtered by name, email or car."""
    params: tuple = ()
    flt = ""
    if q and q.strip():
        flt = "AND (d.name ILIKE %s OR d.email ILIKE %s OR d.car ILIKE %s)"
        params = (_like(q.strip()),) * 3
    with pool.connection() as conn:
        rows = conn.execute(_DRIVER_INFO_SQL.format(filter=flt), params).fetchall()
    return [DriverInfo(**r) for r in rows]


def get_driver_info(pool: ConnectionPool, driver_id: int) -> DriverInfo | None:
    """A driver by id; None for unknown ids and for admin accounts."""
    with pool.connection() as conn:
        row = conn.execute(_DRIVER_INFO_SQL.format(filter="AND d.id = %s"), (driver_id,)).fetchone()
    return DriverInfo(**row) if row else None


# Columns an admin may change (also guards the dynamic SQL below)
_ADMIN_EDITABLE = ("name", "car", "default_tz", "default_commission_pct")


def admin_update_driver(pool: ConnectionPool, driver_id: int, changes: dict) -> None:
    """Apply profile changes; a new password also ends all of the driver's sessions."""
    columns = {k: v for k, v in changes.items() if k in _ADMIN_EDITABLE}
    if "password" in changes:
        columns["password_hash"] = hash_password(changes["password"])
    if not columns:
        return
    assignments = ", ".join(f"{k} = %s" for k in columns)
    with pool.connection() as conn:  # one transaction: both statements or neither
        conn.execute(
            f"UPDATE drivers SET {assignments} WHERE id = %s AND role = 'driver'",
            (*columns.values(), driver_id),
        )
        if "password_hash" in columns:
            conn.execute("DELETE FROM sessions WHERE driver_id = %s", (driver_id,))
