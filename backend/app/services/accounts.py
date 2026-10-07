import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from psycopg_pool import ConnectionPool
from pydantic_core import PydanticCustomError

from app.core.errors import DomainValidationError
from app.core.security import hash_password, verify_password
from app.repositories import drivers as drivers_repo
from app.repositories import users as users_repo
from app.schemas.accounts import DriverCreate, DriverInfo, Profile
from app.schemas.common import check_password

log = logging.getLogger(__name__)

SESSION_TTL = timedelta(days=30)

# Verified against when the email is unknown, so a login attempt takes the same
# time whether or not the account exists (no account enumeration via timing).
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def _token_hash(token: str) -> str:
    # Only a hash of the session token is stored: a leaked sessions table
    # cannot be used to log in.
    return hashlib.sha256(token.encode()).hexdigest()


# --- login and sessions ---

def authenticate(pool: ConnectionPool, email: str, password: str) -> int | None:
    with pool.connection() as conn:
        row = users_repo.find_by_email(conn, email)
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return row["id"] if verify_password(password, row["password_hash"]) else None


def create_session(pool: ConnectionPool, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with pool.connection() as conn:
        users_repo.insert_session(conn, _token_hash(token), user_id,
                                  datetime.now(timezone.utc) + SESSION_TTL)
    return token


def account_by_session(pool: ConnectionPool, token: str) -> dict | None:
    """{"id", "role"} for a live session, None for unknown or expired tokens."""
    with pool.connection() as conn:
        row = users_repo.find_session(conn, _token_hash(token))
        if row and not row["alive"]:
            users_repo.delete_session(conn, _token_hash(token))
            return None
    return {"id": row["id"], "role": row["role"]} if row else None


def end_session(pool: ConnectionPool, token: str) -> None:
    with pool.connection() as conn:
        users_repo.delete_session(conn, _token_hash(token))


# --- profiles ---

def get_profile(pool: ConnectionPool, user_id: int) -> Profile:
    with pool.connection() as conn:
        return drivers_repo.get_profile(conn, user_id)


def set_timezone(pool: ConnectionPool, driver_id: int, tz: str) -> Profile:
    with pool.connection() as conn:
        drivers_repo.update_profile(conn, driver_id, {"default_tz": tz})
        return drivers_repo.get_profile(conn, driver_id)


# --- accounts managed by the admin ---

def create_driver(pool: ConnectionPool, data: DriverCreate) -> int:
    """The account and its profile in one transaction: both or neither."""
    # Explicit transaction: the repositories' savepoints would otherwise commit on their own
    # when they run first on a fresh connection
    with pool.connection() as conn, conn.transaction():
        user_id = users_repo.insert(conn, data.email, hash_password(data.password), "driver")
        drivers_repo.insert_profile(conn, user_id, data.name, data.car_model, data.car_plate,
                                    data.default_tz, data.default_commission_pct)
    return user_id


def update_driver(pool: ConnectionPool, driver_id: int, changes: dict) -> DriverInfo:
    """Apply profile changes; a new password also ends all of the driver's sessions."""
    with pool.connection() as conn, conn.transaction():
        if "password" in changes:
            email = drivers_repo.get_profile(conn, driver_id).email
            try:
                check_password(changes["password"], email)
            except PydanticCustomError as e:
                raise DomainValidationError("password", e.type, e.message())
        drivers_repo.update_profile(conn, driver_id, changes)
        if "password" in changes:
            users_repo.set_password_hash(conn, driver_id, hash_password(changes["password"]))
            users_repo.delete_sessions_of(conn, driver_id)
        return drivers_repo.get_with_totals(conn, driver_id)


def delete_driver(pool: ConnectionPool, driver_id: int) -> bool:
    with pool.connection() as conn:
        return users_repo.delete_driver(conn, driver_id)


def list_drivers(pool: ConnectionPool, q: str | None = None) -> list[DriverInfo]:
    with pool.connection() as conn:
        return drivers_repo.list_with_totals(conn, q)


def get_driver(pool: ConnectionPool, driver_id: int) -> DriverInfo | None:
    """A driver by id; None for unknown ids and for admin accounts."""
    with pool.connection() as conn:
        return drivers_repo.get_with_totals(conn, driver_id)


def ensure_admin(pool: ConnectionPool, email: str, password: str) -> bool:
    """Create an admin account unless the email is already taken. Returns True if created."""
    with pool.connection() as conn:
        existing = users_repo.find_by_email(conn, email)
        if existing:
            if existing["role"] != "admin":
                # Never silently promote an existing driver account
                log.warning("%s belongs to a driver account; admin not created", email)
            return False
        users_repo.insert(conn, email, hash_password(password), "admin")
    return True
