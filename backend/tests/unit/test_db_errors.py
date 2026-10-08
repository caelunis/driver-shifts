import psycopg
from psycopg import errors
from psycopg_pool import PoolTimeout

from app.db.errors import is_db_unavailable


def test_lost_connection_and_pool_timeout_mean_unavailable():
    assert is_db_unavailable(psycopg.OperationalError("connection refused"))  # no SQLSTATE
    assert is_db_unavailable(PoolTimeout("no connection in time"))
    assert is_db_unavailable(errors.AdminShutdown())


def test_errors_of_a_working_database_do_not():
    # Both are OperationalErrors in psycopg, but the database is up
    assert not is_db_unavailable(errors.DeadlockDetected())
    assert not is_db_unavailable(errors.QueryCanceled())
    assert not is_db_unavailable(errors.UniqueViolation())
    assert not is_db_unavailable(ValueError("unrelated"))
