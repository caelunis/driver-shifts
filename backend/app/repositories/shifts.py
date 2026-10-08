"""Shifts: a driver's working periods."""

from datetime import date, datetime
from uuid import UUID

from psycopg.rows import DictRow

from app.core.ids import uuid7
from app.domain.models import Shift
from app.repositories.base import Repository, offset_min, restore_offset

_COLUMNS = (
    "id, driver_id, started_at, ended_at, started_at_offset_minutes, ended_at_offset_minutes, work_date, note"
)


def _shift(row: DictRow) -> Shift:
    """Times in the offsets the client sent them in."""
    ended_at = row["ended_at"]
    return Shift(
        id=row["id"],
        driver_id=row["driver_id"],
        started_at=restore_offset(row["started_at"], row["started_at_offset_minutes"]),
        ended_at=restore_offset(ended_at, row["ended_at_offset_minutes"]) if ended_at is not None else None,
        work_date=row["work_date"],
        note=row["note"],
    )


def _offsets(started_at: datetime, ended_at: datetime | None) -> tuple[int, int | None, date]:
    # started_at.date() is the local date in the start's own offset
    return offset_min(started_at), offset_min(ended_at) if ended_at else None, started_at.date()


class ShiftRepository(Repository):
    async def insert(
        self, driver_id: UUID, started_at: datetime, ended_at: datetime | None, note: str
    ) -> Shift:
        start_off, end_off, work_date = _offsets(started_at, ended_at)
        row = await self._one(
            f"INSERT INTO shifts (id, driver_id, started_at, ended_at, started_at_offset_minutes,"
            f" ended_at_offset_minutes, work_date, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            f" RETURNING {_COLUMNS}",
            (uuid7(), driver_id, started_at, ended_at, start_off, end_off, work_date, note),
        )
        assert row is not None  # noqa: S101 - RETURNING always yields the row
        return _shift(row)

    async def get(self, driver_id: UUID, shift_id: UUID, *, for_update: bool = False) -> Shift | None:
        """A shift of this driver. FOR UPDATE serializes closing a shift with adding trips to it."""
        lock = " FOR UPDATE" if for_update else ""
        row = await self._one(
            f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND id = %s{lock}", (driver_id, shift_id)
        )
        return _shift(row) if row else None

    async def get_open(self, driver_id: UUID) -> Shift | None:
        row = await self._one(
            f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND ended_at IS NULL", (driver_id,)
        )
        return _shift(row) if row else None

    async def for_day(self, driver_id: UUID, work_date: date) -> list[Shift]:
        rows = await self._all(
            f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND work_date = %s ORDER BY started_at",
            (driver_id, work_date),
        )
        return [_shift(r) for r in rows]

    async def update(
        self, shift_id: UUID, started_at: datetime, ended_at: datetime | None, note: str
    ) -> Shift:
        start_off, end_off, work_date = _offsets(started_at, ended_at)
        row = await self._one(
            f"UPDATE shifts SET started_at = %s, ended_at = %s, started_at_offset_minutes = %s,"
            f" ended_at_offset_minutes = %s, work_date = %s, note = %s WHERE id = %s RETURNING {_COLUMNS}",
            (started_at, ended_at, start_off, end_off, work_date, note, shift_id),
        )
        assert row is not None  # noqa: S101 - the caller holds the row locked
        return _shift(row)

    async def delete(self, shift_id: UUID) -> None:
        """The shift's trips go with it (ON DELETE CASCADE)."""
        await self._run("DELETE FROM shifts WHERE id = %s", (shift_id,))

    async def trips_span(self, shift_id: UUID) -> tuple[datetime | None, datetime | None]:
        """Start of the first trip and end of the last one; (None, None) for an empty shift."""
        row = await self._one(
            "SELECT min(started_at) AS first, max(ended_at) AS last FROM trips WHERE shift_id = %s",
            (shift_id,),
        )
        return (row["first"], row["last"]) if row else (None, None)
