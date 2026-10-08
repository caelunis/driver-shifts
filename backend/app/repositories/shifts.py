"""Shifts: a driver's working periods."""

from datetime import date, datetime

from psycopg.rows import DictRow

from app.domain.models import Shift
from app.repositories.base import Repository, offset_min, restore_offset

_COLUMNS = "id, driver_id, started_at, ended_at, start_offset_min, end_offset_min, local_day, note"


def _shift(row: DictRow) -> Shift:
    """Times in the offsets the client sent them in."""
    return Shift(
        id=row["id"],
        driver_id=row["driver_id"],
        start=restore_offset(row["started_at"], row["start_offset_min"]),
        end=(restore_offset(row["ended_at"], row["end_offset_min"]) if row["ended_at"] is not None else None),
        local_day=row["local_day"],
        note=row["note"],
    )


def _offsets(start: datetime, end: datetime | None) -> tuple[int, int | None, date]:
    # start.date() is the local day in the start's own offset
    return offset_min(start), offset_min(end) if end else None, start.date()


class ShiftRepository(Repository):
    async def insert(self, driver_id: int, start: datetime, end: datetime | None, note: str) -> Shift:
        start_off, end_off, day = _offsets(start, end)
        row = await self._one(
            f"INSERT INTO shifts (driver_id, started_at, ended_at, start_offset_min, end_offset_min,"
            f" local_day, note) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {_COLUMNS}",
            (driver_id, start, end, start_off, end_off, day, note),
        )
        assert row is not None  # noqa: S101 - RETURNING always yields the row
        return _shift(row)

    async def get(self, driver_id: int, shift_id: int, *, for_update: bool = False) -> Shift | None:
        """A shift of this driver. FOR UPDATE serializes closing a shift with adding trips to it."""
        lock = " FOR UPDATE" if for_update else ""
        row = await self._one(
            f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND id = %s{lock}", (driver_id, shift_id)
        )
        return _shift(row) if row else None

    async def get_open(self, driver_id: int) -> Shift | None:
        row = await self._one(
            f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND ended_at IS NULL", (driver_id,)
        )
        return _shift(row) if row else None

    async def for_day(self, driver_id: int, day: date) -> list[Shift]:
        rows = await self._all(
            f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND local_day = %s ORDER BY started_at",
            (driver_id, day),
        )
        return [_shift(r) for r in rows]

    async def update(self, shift_id: int, start: datetime, end: datetime | None, note: str) -> Shift:
        start_off, end_off, day = _offsets(start, end)
        row = await self._one(
            f"UPDATE shifts SET started_at = %s, ended_at = %s, start_offset_min = %s,"
            f" end_offset_min = %s, local_day = %s, note = %s WHERE id = %s RETURNING {_COLUMNS}",
            (start, end, start_off, end_off, day, note, shift_id),
        )
        assert row is not None  # noqa: S101 - the caller holds the row locked
        return _shift(row)

    async def delete(self, shift_id: int) -> None:
        """The shift's trips go with it (ON DELETE CASCADE)."""
        await self._run("DELETE FROM shifts WHERE id = %s", (shift_id,))

    async def trips_span(self, shift_id: int) -> tuple[datetime | None, datetime | None]:
        """Start of the first trip and end of the last one; (None, None) for an empty shift."""
        row = await self._one(
            "SELECT min(start_at) AS first, max(end_at) AS last FROM trips WHERE shift_id = %s", (shift_id,)
        )
        return (row["first"], row["last"]) if row else (None, None)
