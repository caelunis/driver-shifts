from datetime import date, datetime, timedelta, timezone

from psycopg_pool import ConnectionPool

from .models import DayInfo, Trip


class TripConflict(Exception):
    """A trip with this id already exists, but with different data."""

    def __init__(self, existing: Trip):
        self.existing = existing


def _offset_min(dt: datetime) -> int:
    return int(dt.utcoffset().total_seconds() // 60)


def _restore(instant: datetime, offset_min: int) -> datetime:
    """Return the instant in the offset the client originally sent."""
    return instant.astimezone(timezone(timedelta(minutes=offset_min)))


def _row_to_trip(row: dict) -> Trip:
    return Trip(
        id=row["id"],
        start=_restore(row["start_at"], row["start_offset_min"]),
        end=_restore(row["end_at"], row["end_offset_min"]),
        amount=row["amount"],
        payment=row["payment"],
        commission=row["commission"],
    )


_TRIP_COLUMNS = "id, start_at, end_at, start_offset_min, end_offset_min, amount, payment, commission"


class TripStorage:
    """Trips in PostgreSQL. Every query is scoped to a single driver."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def for_day(self, driver_id: int, day: date) -> list[Trip]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_TRIP_COLUMNS} FROM trips"
                " WHERE driver_id = %s AND local_day = %s ORDER BY start_at",
                (driver_id, day),
            ).fetchall()
        return [_row_to_trip(r) for r in rows]

    def days(self, driver_id: int) -> list[DayInfo]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT local_day AS date, count(*) AS count, sum(amount - commission) AS net"
                " FROM trips WHERE driver_id = %s GROUP BY local_day ORDER BY local_day",
                (driver_id,),
            ).fetchall()
        return [DayInfo(**r) for r in rows]

    def get(self, driver_id: int, trip_id: str) -> Trip | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_TRIP_COLUMNS} FROM trips WHERE driver_id = %s AND id = %s",
                (driver_id, trip_id),
            ).fetchone()
        return _row_to_trip(row) if row else None

    def add(self, driver_id: int, trip: Trip) -> tuple[Trip, bool]:
        """Idempotent insert. Returns (trip, created).

        The primary key (driver_id, id) makes this safe under concurrency:
        of several simultaneous inserts exactly one wins, the rest see the
        existing row and are compared against it.
        """
        with self.pool.connection() as conn:
            inserted = conn.execute(
                "INSERT INTO trips (driver_id, id, start_at, end_at, start_offset_min,"
                " end_offset_min, local_day, amount, payment, commission)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (driver_id, id) DO NOTHING RETURNING id",
                (
                    driver_id, trip.id, trip.start, trip.end,
                    _offset_min(trip.start), _offset_min(trip.end), trip.local_day,
                    trip.amount, trip.payment, trip.commission,
                ),
            ).fetchone()
        if inserted:
            return trip, True

        existing = self.get(driver_id, trip.id)
        if existing.same_content(trip):
            return existing, False
        raise TripConflict(existing)
