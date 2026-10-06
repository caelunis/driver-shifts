from psycopg_pool import ConnectionPool

from .security import hash_password


def create_driver(pool: ConnectionPool, email: str, password: str, name: str = "") -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO drivers (email, password_hash, name) VALUES (%s, %s, %s) RETURNING id",
            (email.lower(), hash_password(password), name),
        ).fetchone()
    return row["id"]
