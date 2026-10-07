from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def open_pool(conninfo: str, timeout: float = 10.0) -> ConnectionPool:
    """Open a connection pool and wait until the database is reachable.

    The schema is managed by dbmate migrations (backend/db/migrations), never by the app.
    A connection taken with `with pool.connection() as conn:` is one transaction:
    committed on exit, rolled back on an exception. Caveat: `conn.transaction()` as the
    first statement on such a connection is a real transaction that commits on its own,
    not a savepoint; services that need several writes to be atomic open
    `conn.transaction()` themselves first.
    """
    pool = ConnectionPool(
        conninfo, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
    )
    pool.open(wait=True, timeout=timeout)
    return pool
