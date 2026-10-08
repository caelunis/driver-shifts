import psycopg
from psycopg_pool import PoolTimeout

# SQLSTATEs of a server going away: admin_shutdown, crash_shutdown, cannot_connect_now
_SERVER_GOING_AWAY = frozenset({"57P01", "57P02", "57P03"})


def is_db_unavailable(exc: BaseException) -> bool:
    """The database cannot be reached, as opposed to a query that failed on a working one.

    psycopg derives every SQLSTATE error (deadlocks, cancelled queries, …) from
    OperationalError, so the class alone says little; the SQLSTATE decides. No SQLSTATE
    means libpq lost or never got the connection; class 08 is a connection exception.
    """
    if isinstance(exc, PoolTimeout):
        return True
    if not isinstance(exc, psycopg.OperationalError):
        return False
    state = exc.sqlstate
    return state is None or state.startswith("08") or state in _SERVER_GOING_AWAY
