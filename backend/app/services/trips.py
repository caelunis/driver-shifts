from datetime import date

from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.core.enums import ErrorCode
from app.core.errors import ConflictError, DomainValidationError, NotFoundError, TripConflictError
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
        raise DomainValidationError("shift_id", ErrorCode.SHIFT_NOT_FOUND, "No such shift")
    if not by_admin and shift["end"] is not None:
        # A shift older than the window is locked for the driver
        shifts_service.check_within_window("shift_id", shift["end"])
    if trip.start < shift["start"]:
        raise DomainValidationError(
            "start",
            ErrorCode.OUTSIDE_SHIFT,
            "The trip starts before the shift",
            shift_start=shift["start"].isoformat(),
        )
    if shift["end"] is not None and trip.end > shift["end"]:
        raise DomainValidationError(
            "end",
            ErrorCode.OUTSIDE_SHIFT,
            "The trip ends after the shift",
            shift_end=shift["end"].isoformat(),
        )
    shifts_service.check_not_in_future("end", trip.end)


def _check_no_overlap(conn, driver_id: int, trip: Trip) -> None:
    # Also enforced by the trips_no_overlap constraint; checked first to name the other trip.
    # The id itself is excluded, so resending the same trip stays idempotent.
    other = trips_repo.overlapping(conn, driver_id, trip.start, trip.end, trip.id)
    if other is not None:
        raise ConflictError(ErrorCode.TRIP_OVERLAP, "Overlaps another trip of this driver", trip_id=other)


def add(
    pool: ConnectionPool, driver_id: int, trip_in: TripIn, *, by_admin: bool = False
) -> tuple[Trip, bool]:
    """Idempotent insert into one of the driver's shifts. Returns (trip, created).

    The same trip sent again returns the stored one (created=False); a different
    trip under an existing id raises TripConflictError.
    """
    with pool.connection() as conn:
        # FOR UPDATE: a concurrent close of this shift waits, so the trip cannot end up
        # outside a shift that was closed meanwhile
        shift = shifts_repo.get(conn, driver_id, trip_in.shift_id, for_update=True)
        _check_fits_shift(trip_in, shift, by_admin)
        pct = drivers_repo.commission_pct(conn, driver_id)
        trip = resolve_commission(trip_in, pct).to_trip()
        # Remember the percent: editing the amount later recomputes with this one
        trip.commission_pct = float(pct) if pct is not None else None
        _check_no_overlap(conn, driver_id, trip)
        if trips_repo.insert_if_absent(conn, driver_id, trip):
            return trip, True
        existing = trips_repo.get(conn, driver_id, trip.id)
    if existing.same_content(trip):
        return existing, False
    raise TripConflictError(existing)


def _validated(data: dict) -> TripIn:
    """Re-check the merged trip; reports the first error like a body validation error."""
    try:
        return TripIn.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        raise DomainValidationError(str(err["loc"][0]), err["type"], err["msg"]) from e


def update(
    pool: ConnectionPool, driver_id: int, trip_id: str, changes: dict, *, by_admin: bool = False
) -> Trip:
    """Apply `changes` (only the fields the client sent) under the same rules as adding.

    The commission follows the percent stored with the trip: a new amount recomputes it,
    and a commission the client sends must match. A trip entered without a percent keeps
    a hand-entered commission, which must stay below the amount.
    """
    with pool.connection() as conn:
        current = trips_repo.get(conn, driver_id, trip_id)
        if current is None:
            raise NotFoundError()
        # Shifts are locked before the trip, in id order, the same order adding a trip
        # and changing a shift use, so concurrent requests wait instead of deadlocking
        target_id = changes.get("shift_id", current.shift_id)
        shifts = {
            i: shifts_repo.get(conn, driver_id, i, for_update=True)
            for i in sorted({current.shift_id, target_id})
        }
        current = trips_repo.get(conn, driver_id, trip_id, for_update=True)
        if current is None:
            raise NotFoundError()
        if current.shift_id not in shifts:
            raise ConflictError(ErrorCode.TRIP_CHANGED, "The trip was moved meanwhile, try again")
        if not by_admin:
            shifts_service.check_editable(shifts[current.shift_id])

        merged = current.model_dump(exclude={"commission_pct"}) | changes
        if "commission" not in changes and current.commission_pct is not None:
            merged["commission"] = None  # recomputed below
        trip_in = _validated(merged)
        _check_fits_shift(trip_in, shifts[target_id], by_admin)
        trip = resolve_commission(trip_in, current.commission_pct).to_trip()
        trip.commission_pct = current.commission_pct
        _check_no_overlap(conn, driver_id, trip)
        trips_repo.update(conn, driver_id, trip)
        return trip


def delete(pool: ConnectionPool, driver_id: int, trip_id: str, *, by_admin: bool = False) -> None:
    with pool.connection() as conn:
        current = trips_repo.get(conn, driver_id, trip_id)
        if current is None:
            raise NotFoundError()
        shift = shifts_repo.get(conn, driver_id, current.shift_id, for_update=True)
        if shift is None:
            raise NotFoundError()
        if not by_admin:
            shifts_service.check_editable(shift)
        trips_repo.delete(conn, driver_id, trip_id)
