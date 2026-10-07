"""SQL for trips. Every function takes a connection; transactions belong to the caller."""
from datetime import date, datetime, timedelta, timezone

from psycopg import Connection

from app.schemas.trips import DayInfo, Trip


def offset_min(dt: datetime) -> int:
    return int(dt.utcoffset().total_seconds() // 60)


def restore_offset(instant: datetime, offset_minutes: int) -> datetime:
    """timestamptz comes back in UTC; return it in the offset the client originally sent."""
    return instant.astimezone(timezone(timedelta(minutes=offset_minutes)))


def _row_to_trip(row: dict) -> Trip:
    # model_construct skips validation: rows were validated on insert, and re-checking
    # them against today's rules could make old rows unreadable.
    return Trip.model_construct(
        id=row["id"],
        shift_id=row["shift_id"],
        start=restore_offset(row["start_at"], row["start_offset_min"]),
        end=restore_offset(row["end_at"], row["end_offset_min"]),
        amount=row["amount"],
        payment=row["payment"],
        commission=row["commission"],
        commission_pct=(float(row["commission_pct"])
                        if row["commission_pct"] is not None else None),
    )


_COLUMNS = ("t.id, t.shift_id, t.start_at, t.end_at, t.start_offset_min, t.end_offset_min,"
            " t.amount, t.payment, t.commission, t.commission_pct")


def for_day(conn: Connection, driver_id: int, day: date) -> list[Trip]:
    """Trips of the shifts that started on this local day (a night shift keeps its trips
    after midnight)."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM trips t JOIN shifts s ON s.id = t.shift_id"
        " WHERE s.driver_id = %s AND s.local_day = %s ORDER BY t.start_at",
        (driver_id, day),
    ).fetchall()
    return [_row_to_trip(r) for r in rows]


def for_shifts(conn: Connection, shift_ids: list[int]) -> list[Trip]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM trips t WHERE t.shift_id = ANY(%s) ORDER BY t.start_at",
        (shift_ids,),
    ).fetchall()
    return [_row_to_trip(r) for r in rows]


def days(conn: Connection, driver_id: int) -> list[DayInfo]:
    """Days with at least one shift, with the number of trips and the take-home."""
    rows = conn.execute(
        "SELECT s.local_day AS date, count(t.id) AS count,"
        " coalesce(sum(t.amount - t.commission), 0) AS net"
        " FROM shifts s LEFT JOIN trips t ON t.shift_id = s.id"
        " WHERE s.driver_id = %s GROUP BY s.local_day ORDER BY s.local_day",
        (driver_id,),
    ).fetchall()
    return [DayInfo(**r) for r in rows]


def get(conn: Connection, driver_id: int, trip_id: str, *,
        for_update: bool = False) -> Trip | None:
    lock = " FOR UPDATE" if for_update else ""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM trips t WHERE t.driver_id = %s AND t.id = %s{lock}",
        (driver_id, trip_id),
    ).fetchone()
    return _row_to_trip(row) if row else None


def overlapping(conn: Connection, driver_id: int, start: datetime, end: datetime,
                exclude_id: str) -> str | None:
    """Id of another trip of the driver that overlaps [start, end), if any."""
    row = conn.execute(
        "SELECT id FROM trips WHERE driver_id = %s AND id <> %s"
        " AND tstzrange(start_at, end_at, '[)') && tstzrange(%s, %s, '[)') LIMIT 1",
        (driver_id, exclude_id, start, end),
    ).fetchone()
    return row["id"] if row else None


def insert_if_absent(conn: Connection, driver_id: int, trip: Trip) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING on (driver_id, id). True if the row was inserted.

    Safe under concurrency: of several simultaneous inserts exactly one wins.
    """
    row = conn.execute(
        "INSERT INTO trips (driver_id, id, shift_id, start_at, end_at, start_offset_min,"
        " end_offset_min, amount, payment, commission, commission_pct)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (driver_id, id) DO NOTHING RETURNING id",
        (
            driver_id, trip.id, trip.shift_id, trip.start, trip.end,
            offset_min(trip.start), offset_min(trip.end),
            trip.amount, trip.payment, trip.commission, trip.commission_pct,
        ),
    ).fetchone()
    return row is not None


def update(conn: Connection, driver_id: int, trip: Trip) -> None:
    """Overwrite every editable column of the trip `trip.id`."""
    conn.execute(
        "UPDATE trips SET shift_id = %s, start_at = %s, end_at = %s, start_offset_min = %s,"
        " end_offset_min = %s, amount = %s, payment = %s, commission = %s, commission_pct = %s"
        " WHERE driver_id = %s AND id = %s",
        (
            trip.shift_id, trip.start, trip.end, offset_min(trip.start), offset_min(trip.end),
            trip.amount, trip.payment, trip.commission, trip.commission_pct,
            driver_id, trip.id,
        ),
    )


def delete(conn: Connection, driver_id: int, trip_id: str) -> None:
    conn.execute("DELETE FROM trips WHERE driver_id = %s AND id = %s", (driver_id, trip_id))
