"""Trips. Every trip belongs to a shift of the same driver."""

from datetime import date, datetime

from psycopg.rows import DictRow

from app.core.enums import PaymentMethod
from app.domain.models import DayInfo, Trip
from app.repositories.base import Repository, offset_min, restore_offset

_COLUMNS = (
    "t.id, t.driver_id, t.shift_id, t.start_at, t.end_at, t.start_offset_min, t.end_offset_min,"
    " t.amount, t.payment, t.commission, t.commission_pct"
)


def _trip(row: DictRow) -> Trip:
    # Rows are not re-validated against today's rules: they were valid when stored,
    # and a stricter rule must not make old rows unreadable.
    return Trip(
        id=row["id"],
        driver_id=row["driver_id"],
        shift_id=row["shift_id"],
        start=restore_offset(row["start_at"], row["start_offset_min"]),
        end=restore_offset(row["end_at"], row["end_offset_min"]),
        amount=row["amount"],
        payment=PaymentMethod(row["payment"]),
        commission=row["commission"],
        commission_pct=row["commission_pct"],
    )


class TripRepository(Repository):
    async def for_day(self, driver_id: int, day: date) -> list[Trip]:
        """Trips of the shifts that started on this local day (a night shift keeps its trips
        after midnight)."""
        rows = await self._all(
            f"SELECT {_COLUMNS} FROM trips t JOIN shifts s ON s.id = t.shift_id"
            " WHERE s.driver_id = %s AND s.local_day = %s ORDER BY t.start_at",
            (driver_id, day),
        )
        return [_trip(r) for r in rows]

    async def for_shifts(self, shift_ids: list[int]) -> list[Trip]:
        rows = await self._all(
            f"SELECT {_COLUMNS} FROM trips t WHERE t.shift_id = ANY(%s) ORDER BY t.start_at", (shift_ids,)
        )
        return [_trip(r) for r in rows]

    async def days(self, driver_id: int) -> list[DayInfo]:
        """Days with at least one shift, with the number of trips and the take-home."""
        rows = await self._all(
            "SELECT s.local_day AS date, count(t.id) AS count,"
            " coalesce(sum(t.amount - t.commission), 0) AS net"
            " FROM shifts s LEFT JOIN trips t ON t.shift_id = s.id"
            " WHERE s.driver_id = %s GROUP BY s.local_day ORDER BY s.local_day",
            (driver_id,),
        )
        return [DayInfo(date=r["date"], count=r["count"], net=r["net"]) for r in rows]

    async def get(self, driver_id: int, trip_id: str, *, for_update: bool = False) -> Trip | None:
        lock = " FOR UPDATE" if for_update else ""
        row = await self._one(
            f"SELECT {_COLUMNS} FROM trips t WHERE t.driver_id = %s AND t.id = %s{lock}", (driver_id, trip_id)
        )
        return _trip(row) if row else None

    async def overlapping(
        self, driver_id: int, start: datetime, end: datetime, exclude_id: str
    ) -> str | None:
        """Id of another trip of the driver that overlaps [start, end), if any."""
        row = await self._one(
            "SELECT id FROM trips WHERE driver_id = %s AND id <> %s"
            " AND tstzrange(start_at, end_at, '[)') && tstzrange(%s, %s, '[)') LIMIT 1",
            (driver_id, exclude_id, start, end),
        )
        return str(row["id"]) if row else None

    async def insert_if_absent(self, trip: Trip) -> bool:
        """INSERT ... ON CONFLICT DO NOTHING on (driver_id, id). True if the row was inserted.

        Safe under concurrency: of several simultaneous inserts exactly one wins.
        """
        row = await self._one(
            "INSERT INTO trips (driver_id, id, shift_id, start_at, end_at, start_offset_min,"
            " end_offset_min, amount, payment, commission, commission_pct)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (driver_id, id) DO NOTHING RETURNING id",
            (
                trip.driver_id,
                trip.id,
                trip.shift_id,
                trip.start,
                trip.end,
                offset_min(trip.start),
                offset_min(trip.end),
                trip.amount,
                trip.payment,
                trip.commission,
                trip.commission_pct,
            ),
        )
        return row is not None

    async def update(self, trip: Trip) -> None:
        """Overwrite every editable column of the trip `trip.id`."""
        await self._run(
            "UPDATE trips SET shift_id = %s, start_at = %s, end_at = %s, start_offset_min = %s,"
            " end_offset_min = %s, amount = %s, payment = %s, commission = %s, commission_pct = %s"
            " WHERE driver_id = %s AND id = %s",
            (
                trip.shift_id,
                trip.start,
                trip.end,
                offset_min(trip.start),
                offset_min(trip.end),
                trip.amount,
                trip.payment,
                trip.commission,
                trip.commission_pct,
                trip.driver_id,
                trip.id,
            ),
        )

    async def delete(self, driver_id: int, trip_id: str) -> None:
        await self._run("DELETE FROM trips WHERE driver_id = %s AND id = %s", (driver_id, trip_id))
