from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA = Path(__file__).with_name("schema.sql")
DEFAULT_DATABASE_URL = "postgresql://shifts:shifts@127.0.0.1:5433/shifts"

# Arbitrary constant for pg_advisory_xact_lock: serializes schema creation
# when several app processes start at the same time.
_SCHEMA_LOCK_ID = 74_210_001


def open_pool(conninfo: str, timeout: float = 10.0) -> ConnectionPool:
    """Open a connection pool and wait until the database is reachable."""
    pool = ConnectionPool(
        conninfo, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
    )
    pool.open(wait=True, timeout=timeout)
    return pool


def init_schema(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_ID,))
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
