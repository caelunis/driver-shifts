"""Database access: an async connection pool and units of work on top of it."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.constants import DB_ACQUIRE_TIMEOUT, DB_CONNECT_TIMEOUT, DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE
from app.repositories.drivers import DriverRepository
from app.repositories.sessions import SessionRepository
from app.repositories.shifts import ShiftRepository
from app.repositories.trips import TripRepository
from app.repositories.users import UserRepository

Connection = AsyncConnection[DictRow]


class UnitOfWork:
    """One transaction and the repositories that work inside it."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.users = UserRepository(conn)
        self.sessions = SessionRepository(conn)
        self.drivers = DriverRepository(conn)
        self.shifts = ShiftRepository(conn)
        self.trips = TripRepository(conn)


class Database:
    """The app's PostgreSQL. The schema belongs to the dbmate migrations
    (backend/db/migrations); nothing here creates or changes it."""

    def __init__(self, pool: AsyncConnectionPool[Connection]) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, conninfo: str, wait_seconds: float = DB_CONNECT_TIMEOUT) -> "Database":
        """Open the pool and wait until the database is reachable."""
        pool = AsyncConnectionPool(
            conninfo,
            min_size=DB_POOL_MIN_SIZE,
            max_size=DB_POOL_MAX_SIZE,
            open=False,
            timeout=DB_ACQUIRE_TIMEOUT,
            connection_class=Connection,
            kwargs={"row_factory": dict_row},
        )
        await pool.open(wait=True, timeout=wait_seconds)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[UnitOfWork]:
        """A transaction: committed when the block ends, rolled back on an exception.

        It is always an explicit transaction. Repositories open savepoints inside it
        (`conn.transaction()`) to turn constraint violations into domain errors; without
        an outer transaction such a savepoint would be a transaction of its own and
        commit by itself.
        """
        async with self._pool.connection() as conn, conn.transaction():
            yield UnitOfWork(conn)

    async def ping(self, wait_seconds: float) -> None:
        async with self._pool.connection(timeout=wait_seconds) as conn:
            await conn.execute("SELECT 1")
