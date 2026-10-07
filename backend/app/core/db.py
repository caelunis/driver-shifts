from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def open_pool(conninfo: str, timeout: float = 10.0) -> ConnectionPool:
    """Open a connection pool and wait until the database is reachable.

    The schema is managed by yoyo migrations (backend/migrations), never by the app.
    A connection taken with `with pool.connection() as conn:` is one transaction:
    committed on exit, rolled back on an exception.
    """
    pool = ConnectionPool(
        conninfo, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
    )
    pool.open(wait=True, timeout=timeout)
    return pool
