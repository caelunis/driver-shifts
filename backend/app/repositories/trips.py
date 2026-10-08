"""Trips. Every trip belongs to a shift of the same driver."""

from datetime import date, datetime
from uuid import UUID

from psycopg.rows import DictRow

from app.core.enums import PaymentMethod
from app.domain.models import DayInfo, Trip
from app.repositories.base import Repository, offset_min, restore_offset

_COLUMNS = (
    "t.id, t.driver_id, t.shift_id, t.started_at, t.ended_at, t.started_at_offset_minutes,"
    " t.ended_at_offset_minutes, t.fare, t.payment_method, t.commission_amount, t.commission_percent"
)


def _trip(row: DictRow) -> Trip:
    # Rows are not re-validated against today's rules: they were valid when stored,
    # and a stricter rule must not make old rows unreadable.
    return Trip(
        id=row["id"],
        driver_id=row["driver_id"],
        shift_id=row["shift_id"],
        started_at=restore_offset(row["started_at"], row["started_at_offset_minutes"]),
        ended_at=restore_offset(row["ended_at"], row["ended_at_offset_minutes"]),
        fare=row["fare"],
        payment_method=PaymentMethod(row["payment_method"]),
        commission_amount=row["commission_amount"],
        commission_percent=row["commission_percent"],
    )


class TripRepository(Repository):
    async def for_day(self, driver_id: UUID, work_date: date) -> list[Trip]:
        """Trips of the shifts that started on this work date (a night shift keeps its trips
        after midnight)."""
        rows = await self._all(
            f"SELECT {_COLUMNS} FROM trips t JOIN shifts s ON s.id = t.shift_id"
            " WHERE s.driver_id = %s AND s.work_date = %s ORDER BY t.started_at",
            (driver_id, work_date),
        )
        return [_trip(r) for r in rows]

    async def for_shifts(self, shift_ids: list[UUID]) -> list[Trip]:
        rows = await self._all(
            f"SELECT {_COLUMNS} FROM trips t WHERE t.shift_id = ANY(%s) ORDER BY t.started_at", (shift_ids,)
        )
        return [_trip(r) for r in rows]

    async def days(self, driver_id: UUID) -> list[DayInfo]:
        """Work dates with at least one shift, with the number of trips and the take-home."""
        rows = await self._all(
            "SELECT s.work_date, count(t.id) AS trips_count,"
            " coalesce(sum(t.fare - t.commission_amount), 0) AS net_income"
            " FROM shifts s LEFT JOIN trips t ON t.shift_id = s.id"
            " WHERE s.driver_id = %s GROUP BY s.work_date ORDER BY s.work_date",
            (driver_id,),
        )
        return [DayInfo(r["work_date"], r["trips_count"], r["net_income"]) for r in rows]

    async def get(self, driver_id: UUID, trip_id: UUID, *, for_update: bool = False) -> Trip | None:
        lock = " FOR UPDATE" if for_update else ""
        row = await self._one(
            f"SELECT {_COLUMNS} FROM trips t WHERE t.driver_id = %s AND t.id = %s{lock}", (driver_id, trip_id)
        )
        return _trip(row) if row else None

    async def overlapping(
        self, driver_id: UUID, started_at: datetime, ended_at: datetime, exclude_id: UUID
    ) -> UUID | None:
        """Id of another trip of the driver that overlaps [started_at, ended_at), if any."""
        row = await self._one(
            "SELECT id FROM trips WHERE driver_id = %s AND id <> %s"
            " AND tstzrange(started_at, ended_at, '[)') && tstzrange(%s, %s, '[)') LIMIT 1",
            (driver_id, exclude_id, started_at, ended_at),
        )
        return row["id"] if row else None

    async def insert_if_absent(self, trip: Trip) -> bool:
        """INSERT ... ON CONFLICT DO NOTHING on (driver_id, id). True if the row was inserted.

        Safe under concurrency: of several simultaneous inserts exactly one wins.
        """
        row = await self._one(
            "INSERT INTO trips (driver_id, id, shift_id, started_at, ended_at, started_at_offset_minutes,"
            " ended_at_offset_minutes, fare, payment_method, commission_amount, commission_percent)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (driver_id, id) DO NOTHING RETURNING id",
            (
                trip.driver_id,
                trip.id,
                trip.shift_id,
                trip.started_at,
                trip.ended_at,
                offset_min(trip.started_at),
                offset_min(trip.ended_at),
                trip.fare,
                trip.payment_method,
                trip.commission_amount,
                trip.commission_percent,
            ),
        )
        return row is not None

    async def update(self, trip: Trip) -> None:
        """Overwrite every editable column of the trip `trip.id`."""
        await self._run(
            "UPDATE trips SET shift_id = %s, started_at = %s, ended_at = %s, started_at_offset_minutes = %s,"
            " ended_at_offset_minutes = %s, fare = %s, payment_method = %s, commission_amount = %s,"
            " commission_percent = %s WHERE driver_id = %s AND id = %s",
            (
                trip.shift_id,
                trip.started_at,
                trip.ended_at,
                offset_min(trip.started_at),
                offset_min(trip.ended_at),
                trip.fare,
                trip.payment_method,
                trip.commission_amount,
                trip.commission_percent,
                trip.driver_id,
                trip.id,
            ),
        )

    async def delete(self, driver_id: UUID, trip_id: UUID) -> None:
        await self._run("DELETE FROM trips WHERE driver_id = %s AND id = %s", (driver_id, trip_id))
