"""Shifts: a driver's working periods. Every trip belongs to a shift."""
from datetime import date, datetime, timedelta

from psycopg.errors import ExclusionViolation, UniqueViolation
from psycopg_pool import ConnectionPool

from app.core import clock
from app.core.errors import Conflict, DomainValidationError, NotFound
from app.repositories import drivers as drivers_repo
from app.repositories import shifts as shifts_repo
from app.repositories import trips as trips_repo
from app.schemas.common import offset_tz
from app.schemas.shifts import Shift, ShiftDetail
from app.services.summary import shift_summary

MAX_SHIFT = timedelta(hours=24)
# How far back a driver may enter or change shifts; the admin is not limited
BACKFILL_WINDOW = timedelta(days=7)
# Tolerance for client clocks that run slightly ahead
CLOCK_SKEW = timedelta(minutes=5)


def check_not_in_future(field: str, value: datetime) -> None:
    if value > clock.now() + CLOCK_SKEW:
        raise DomainValidationError(field, "in_future", "Time is in the future")


def check_within_window(field: str, value: datetime) -> None:
    if value < clock.now() - BACKFILL_WINDOW:
        raise DomainValidationError(field, "too_old", "Older than the allowed window",
                                    days=BACKFILL_WINDOW.days)


def _check_end(start: datetime, end: datetime) -> None:
    if end <= start:
        raise DomainValidationError("end", "end_before_start", "End must be later than start")
    if end - start > MAX_SHIFT:
        raise DomainValidationError("end", "shift_too_long", "A shift lasts at most 24 hours",
                                    hours=24)
    check_not_in_future("end", end)


def _to_model(shift: dict, trips: list, detail: bool = False) -> Shift:
    # An open shift is summarized up to now, in the shift's own offset
    end = shift["end"] or clock.now().astimezone(shift["start"].tzinfo)
    model = ShiftDetail if detail else Shift
    extra = {"trips": trips} if detail else {}
    return model(
        id=shift["id"], start=shift["start"], end=shift["end"],
        status="open" if shift["end"] is None else "closed",
        local_day=shift["local_day"], note=shift["note"],
        summary=shift_summary(trips, shift["start"], end), **extra,
    )


def start(pool: ConnectionPool, driver_id: int, start_at: datetime | None = None,
          end_at: datetime | None = None, note: str = "", *, by_admin: bool = False) -> Shift:
    """Start a shift now, at `start_at`, or enter a finished past shift (`start_at` + `end_at`)."""
    with pool.connection() as conn:
        if start_at is None:
            tz = offset_tz(drivers_repo.get_profile(conn, driver_id).default_tz)
            start_at = clock.now().astimezone(tz)
        check_not_in_future("start", start_at)
        if not by_admin:
            check_within_window("start", start_at)
        if end_at is not None:
            _check_end(start_at, end_at)
        elif shifts_repo.get_open(conn, driver_id):
            raise Conflict("shift_already_open", "Close the open shift first")
        try:
            with conn.transaction():
                shift = shifts_repo.insert(conn, driver_id, start_at, end_at, note)
        except (ExclusionViolation, UniqueViolation):
            # Also covers a race with another request that opened a shift meanwhile
            raise Conflict("shift_overlap", "Overlaps another shift of this driver")
        return _to_model(shift, [])


def close(pool: ConnectionPool, driver_id: int, shift_id: int,
          end_at: datetime | None = None) -> Shift:
    """Close an open shift. Allowed however long ago it started: the end time is checked
    against the 24-hour limit instead, so a forgotten shift can always be closed."""
    with pool.connection() as conn:
        shift = shifts_repo.get(conn, driver_id, shift_id, for_update=True)
        if shift is None:
            raise NotFound()
        if shift["end"] is not None:
            raise Conflict("shift_already_closed", "The shift is already closed")
        if end_at is None:
            end_at = clock.now().astimezone(shift["start"].tzinfo)
        _check_end(shift["start"], end_at)
        last = shifts_repo.last_trip_end(conn, shift_id)
        if last is not None and end_at < last:
            raise DomainValidationError("end", "before_last_trip",
                                        "The shift cannot end before its last trip",
                                        last_trip_end=last.isoformat())
        closed = shifts_repo.close(conn, shift_id, end_at)
        return _to_model(closed, trips_repo.for_shifts(conn, [shift_id]))


def get(pool: ConnectionPool, driver_id: int, shift_id: int) -> ShiftDetail:
    with pool.connection() as conn:
        shift = shifts_repo.get(conn, driver_id, shift_id)
        if shift is None:
            raise NotFound()
        return _to_model(shift, trips_repo.for_shifts(conn, [shift_id]), detail=True)


def current(pool: ConnectionPool, driver_id: int) -> Shift | None:
    with pool.connection() as conn:
        shift = shifts_repo.get_open(conn, driver_id)
        if shift is None:
            return None
        return _to_model(shift, trips_repo.for_shifts(conn, [shift["id"]]))


def for_day(pool: ConnectionPool, driver_id: int, day: date) -> list[Shift]:
    with pool.connection() as conn:
        shifts = shifts_repo.for_day(conn, driver_id, day)
        trips = trips_repo.for_shifts(conn, [s["id"] for s in shifts])
    by_shift: dict[int, list] = {}
    for t in trips:
        by_shift.setdefault(t.shift_id, []).append(t)
    return [_to_model(s, by_shift.get(s["id"], [])) for s in shifts]
