"""SQL for shifts. Every function takes a connection; transactions belong to the caller."""

from datetime import date, datetime

from psycopg import Connection

from app.repositories.trips import offset_min, restore_offset

_COLUMNS = "id, driver_id, started_at, ended_at, start_offset_min, end_offset_min, local_day, note"


def _row(row: dict | None) -> dict | None:
    """Times in the offsets the client sent them in."""
    if row is None:
        return None
    return {
        "id": row["id"],
        "driver_id": row["driver_id"],
        "start": restore_offset(row["started_at"], row["start_offset_min"]),
        "end": (
            restore_offset(row["ended_at"], row["end_offset_min"]) if row["ended_at"] is not None else None
        ),
        "local_day": row["local_day"],
        "note": row["note"],
    }


def insert(conn: Connection, driver_id: int, start: datetime, end: datetime | None, note: str) -> dict:
    row = conn.execute(
        f"INSERT INTO shifts (driver_id, started_at, ended_at, start_offset_min, end_offset_min,"
        f" local_day, note) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {_COLUMNS}",
        (
            driver_id,
            start,
            end,
            offset_min(start),
            offset_min(end) if end else None,
            start.date(),
            note,
        ),  # start.date() is the local day in the start's own offset
    ).fetchone()
    return _row(row)


def get(conn: Connection, driver_id: int, shift_id: int, *, for_update: bool = False) -> dict | None:
    """A shift of this driver. FOR UPDATE serializes closing a shift with adding trips to it."""
    lock = " FOR UPDATE" if for_update else ""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND id = %s{lock}",
        (driver_id, shift_id),
    ).fetchone()
    return _row(row)


def get_open(conn: Connection, driver_id: int) -> dict | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND ended_at IS NULL", (driver_id,)
    ).fetchone()
    return _row(row)


def for_day(conn: Connection, driver_id: int, day: date) -> list[dict]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM shifts WHERE driver_id = %s AND local_day = %s ORDER BY started_at",
        (driver_id, day),
    ).fetchall()
    return [_row(r) for r in rows]


def close(conn: Connection, shift_id: int, end: datetime) -> dict:
    row = conn.execute(
        f"UPDATE shifts SET ended_at = %s, end_offset_min = %s WHERE id = %s RETURNING {_COLUMNS}",
        (end, offset_min(end), shift_id),
    ).fetchone()
    return _row(row)


def update(conn: Connection, shift_id: int, start: datetime, end: datetime | None, note: str) -> dict:
    row = conn.execute(
        f"UPDATE shifts SET started_at = %s, ended_at = %s, start_offset_min = %s,"
        f" end_offset_min = %s, local_day = %s, note = %s WHERE id = %s RETURNING {_COLUMNS}",
        (start, end, offset_min(start), offset_min(end) if end else None, start.date(), note, shift_id),
    ).fetchone()
    return _row(row)


def delete(conn: Connection, shift_id: int) -> None:
    """The shift's trips go with it (ON DELETE CASCADE)."""
    conn.execute("DELETE FROM shifts WHERE id = %s", (shift_id,))


def trips_span(conn: Connection, shift_id: int) -> tuple[datetime | None, datetime | None]:
    """Start of the first trip and end of the last one; (None, None) for an empty shift."""
    row = conn.execute(
        "SELECT min(start_at) AS first, max(end_at) AS last FROM trips WHERE shift_id = %s",
        (shift_id,),
    ).fetchone()
    return row["first"], row["last"]
