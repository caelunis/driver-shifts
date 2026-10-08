"""SQL for accounts (`users`) and their sessions."""

from datetime import datetime

from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.core.enums import Role
from app.core.errors import EmailTakenError


def insert(conn: Connection, email: str, password_hash: str, role: Role) -> int:
    try:
        # A savepoint, so a duplicate does not abort the caller's whole transaction
        with conn.transaction():
            row = conn.execute(
                "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
                (email.lower(), password_hash, role),
            ).fetchone()
    except UniqueViolation as e:
        raise EmailTakenError(email) from e
    return row["id"]


def find_by_email(conn: Connection, email: str) -> dict | None:
    """{"id", "role", "password_hash"} or None."""
    return conn.execute(
        "SELECT id, role, password_hash FROM users WHERE lower(email) = lower(%s)", (email,)
    ).fetchone()


def any_exist(conn: Connection) -> bool:
    return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def set_password_hash(conn: Connection, user_id: int, password_hash: str) -> None:
    conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))


def delete_driver(conn: Connection, user_id: int) -> bool:
    """Delete a driver account (never an admin). The profile, trips and sessions go
    with it via ON DELETE CASCADE."""
    row = conn.execute(
        "DELETE FROM users WHERE id = %s AND role = %s RETURNING id", (user_id, Role.DRIVER)
    ).fetchone()
    return row is not None


# --- sessions ---


def insert_session(conn: Connection, token_hash: str, user_id: int, expires_at: datetime) -> None:
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (token_hash, user_id, expires_at),
    )


def find_session(conn: Connection, token_hash: str) -> dict | None:
    """{"id", "role", "alive"} of the session's account, or None."""
    return conn.execute(
        "SELECT u.id, u.role, s.expires_at > now() AS alive"
        " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = %s",
        (token_hash,),
    ).fetchone()


def delete_session(conn: Connection, token_hash: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))


def delete_sessions_of(conn: Connection, user_id: int) -> None:
    conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
