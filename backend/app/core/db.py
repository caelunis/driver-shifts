from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.constants import DB_CONNECT_TIMEOUT, DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE


def open_pool(conninfo: str, timeout: float = DB_CONNECT_TIMEOUT) -> ConnectionPool:
    """Open a connection pool and wait until the database is reachable.

    The schema is managed by dbmate migrations (backend/db/migrations), never by the app.
    A connection taken with `with pool.connection() as conn:` is one transaction:
    committed on exit, rolled back on an exception. Caveat: `conn.transaction()` as the
    first statement on such a connection is a real transaction that commits on its own,
    not a savepoint; services that need several writes to be atomic open
    `conn.transaction()` themselves first.
    """
    pool = ConnectionPool(
        conninfo,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
        open=False,
        kwargs={"row_factory": dict_row},
    )
    pool.open(wait=True, timeout=timeout)
    return pool
