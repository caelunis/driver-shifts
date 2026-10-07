"""SQL for trips. Every function takes a connection; transactions belong to the caller."""
from datetime import date, datetime, timedelta, timezone

from psycopg import Connection

from app.schemas.trips import DayInfo, Trip


def _offset_min(dt: datetime) -> int:
    return int(dt.utcoffset().total_seconds() // 60)


def _restore(instant: datetime, offset_min: int) -> datetime:
    """Return the instant in the offset the client originally sent."""
    return instant.astimezone(timezone(timedelta(minutes=offset_min)))


def _row_to_trip(row: dict) -> Trip:
    # model_construct skips validation: rows were validated on insert, and re-checking
    # them against today's rules would make old rows (e.g. commission == amount from
    # before that was forbidden) unreadable.
    return Trip.model_construct(
        id=row["id"],
        start=_restore(row["start_at"], row["start_offset_min"]),
        end=_restore(row["end_at"], row["end_offset_min"]),
        amount=row["amount"],
        payment=row["payment"],
        commission=row["commission"],
    )


_COLUMNS = "id, start_at, end_at, start_offset_min, end_offset_min, amount, payment, commission"


def for_day(conn: Connection, driver_id: int, day: date) -> list[Trip]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM trips WHERE driver_id = %s AND local_day = %s ORDER BY start_at",
        (driver_id, day),
    ).fetchall()
    return [_row_to_trip(r) for r in rows]


def days(conn: Connection, driver_id: int) -> list[DayInfo]:
    rows = conn.execute(
        "SELECT local_day AS date, count(*) AS count, sum(amount - commission) AS net"
        " FROM trips WHERE driver_id = %s GROUP BY local_day ORDER BY local_day",
        (driver_id,),
    ).fetchall()
    return [DayInfo(**r) for r in rows]


def get(conn: Connection, driver_id: int, trip_id: str) -> Trip | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM trips WHERE driver_id = %s AND id = %s", (driver_id, trip_id)
    ).fetchone()
    return _row_to_trip(row) if row else None


def insert_if_absent(conn: Connection, driver_id: int, trip: Trip) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING on (driver_id, id). True if the row was inserted.

    Safe under concurrency: of several simultaneous inserts exactly one wins.
    """
    row = conn.execute(
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
    return row is not None
