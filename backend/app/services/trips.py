from datetime import date

from psycopg_pool import ConnectionPool

from app.core import clock
from app.core.errors import DomainValidationError, TripConflict
from app.repositories import drivers as drivers_repo
from app.repositories import shifts as shifts_repo
from app.repositories import trips as trips_repo
from app.schemas.trips import DayInfo, DaySummary, Trip, TripIn
from app.services import shifts as shifts_service
from app.services.commission import resolve_commission
from app.services.summary import day_summary as summarize_day


def days(pool: ConnectionPool, driver_id: int) -> list[DayInfo]:
    with pool.connection() as conn:
        return trips_repo.days(conn, driver_id)


def for_day(pool: ConnectionPool, driver_id: int, day: date) -> list[Trip]:
    with pool.connection() as conn:
        return trips_repo.for_day(conn, driver_id, day)


def day_summary(pool: ConnectionPool, driver_id: int, day: date) -> DaySummary:
    with pool.connection() as conn:
        trips = trips_repo.for_day(conn, driver_id, day)
        shifts = len(shifts_repo.for_day(conn, driver_id, day))
    return summarize_day(trips, day, shifts)


def _check_fits_shift(trip: TripIn, shift: dict, by_admin: bool) -> None:
    if shift is None:
        raise DomainValidationError("shift_id", "shift_not_found", "No such shift")
    if not by_admin and shift["end"] is not None:
        # A shift older than the window is locked for the driver
        shifts_service.check_within_window("shift_id", shift["end"])
    if trip.start < shift["start"]:
        raise DomainValidationError("start", "outside_shift", "The trip starts before the shift",
                                    shift_start=shift["start"].isoformat())
    if shift["end"] is not None and trip.end > shift["end"]:
        raise DomainValidationError("end", "outside_shift", "The trip ends after the shift",
                                    shift_end=shift["end"].isoformat())
    shifts_service.check_not_in_future("end", trip.end)


def add(pool: ConnectionPool, driver_id: int, trip_in: TripIn, *,
        by_admin: bool = False) -> tuple[Trip, bool]:
    """Idempotent insert into one of the driver's shifts. Returns (trip, created).

    The same trip sent again returns the stored one (created=False); a different
    trip under an existing id raises TripConflict.
    """
    with pool.connection() as conn:
        # FOR UPDATE: a concurrent close of this shift waits, so the trip cannot end up
        # outside a shift that was closed meanwhile
        shift = shifts_repo.get(conn, driver_id, trip_in.shift_id, for_update=True)
        _check_fits_shift(trip_in, shift, by_admin)
        pct = drivers_repo.commission_pct(conn, driver_id)
        trip = resolve_commission(trip_in, pct).to_trip()
        if trips_repo.insert_if_absent(conn, driver_id, trip):
            return trip, True
        existing = trips_repo.get(conn, driver_id, trip.id)
    if existing.same_content(trip):
        return existing, False
    raise TripConflict(existing)
