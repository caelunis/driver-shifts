"""What every repository shares. A repository is plain SQL over one connection;
the transaction belongs to the unit of work that created it (app/db/database.py)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import DictRow


class Repository:
    def __init__(self, conn: AsyncConnection[DictRow]) -> None:
        self._conn = conn

    async def _one(self, sql: str, params: tuple[Any, ...] = ()) -> DictRow | None:
        cur = await self._conn.execute(sql, params)
        return await cur.fetchone()

    async def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[DictRow]:
        cur = await self._conn.execute(sql, params)
        return await cur.fetchall()

    async def _run(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Execute; returns the number of affected rows."""
        cur = await self._conn.execute(sql, params)
        return cur.rowcount


# timestamptz keeps the instant and loses the offset the client wrote it with, so the
# offset is stored next to it and put back on the way out.


def offset_min(dt: datetime) -> int:
    offset = dt.utcoffset()
    if offset is None:
        raise ValueError("an aware datetime is required")
    return int(offset.total_seconds() // 60)


def restore_offset(instant: datetime, offset_minutes: int) -> datetime:
    """timestamptz comes back in UTC; return it in the offset the client originally sent."""
    return instant.astimezone(timezone(timedelta(minutes=offset_minutes)))
