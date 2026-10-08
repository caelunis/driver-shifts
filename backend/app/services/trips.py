"""Trips, and the per-day views of a diary."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.core.enums import ErrorCode
from app.core.errors import ConflictError, DomainValidationError, NotFoundError, TripConflictError
from app.db.database import Database, UnitOfWork
from app.domain.models import DayInfo, DaySummary, Shift, Trip
from app.schemas.trips import TripIn
from app.services.commission import Commission
from app.services.policies import ShiftPolicy


def _check_fits_shift(trip: TripIn, shift: Shift | None, by_admin: bool) -> Shift:
    if shift is None:
        raise DomainValidationError("shift_id", ErrorCode.SHIFT_NOT_FOUND, "No such shift")
    if not by_admin and shift.end is not None:
        # A shift older than the window is locked for the driver
        ShiftPolicy.within_window("shift_id", shift.end)
    if trip.start < shift.start:
        raise DomainValidationError(
            "start",
            ErrorCode.OUTSIDE_SHIFT,
            "The trip starts before the shift",
            shift_start=shift.start.isoformat(),
        )
    if shift.end is not None and trip.end > shift.end:
        raise DomainValidationError(
            "end", ErrorCode.OUTSIDE_SHIFT, "The trip ends after the shift", shift_end=shift.end.isoformat()
        )
    ShiftPolicy.not_in_future("end", trip.end)
    return shift


async def _check_no_overlap(uow: UnitOfWork, trip: Trip) -> None:
    # Also enforced by the trips_no_overlap constraint; checked first to name the other trip.
    # The id itself is excluded, so resending the same trip stays idempotent.
    other = await uow.trips.overlapping(trip.driver_id, trip.start, trip.end, trip.id)
    if other is not None:
        raise ConflictError(ErrorCode.TRIP_OVERLAP, "Overlaps another trip of this driver", trip_id=other)


def _validated(data: Mapping[str, Any]) -> TripIn:
    """Re-check a merged trip; reports the first error like a body validation error."""
    try:
        return TripIn.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        raise DomainValidationError(str(err["loc"][0]), err["type"], err["msg"]) from e


def _build(driver_id: int, trip_in: TripIn, trip_id: str, commission: int, pct: Decimal | None) -> Trip:
    return Trip(
        id=trip_id,
        driver_id=driver_id,
        shift_id=trip_in.shift_id,
        start=trip_in.start,
        end=trip_in.end,
        amount=trip_in.amount,
        payment=trip_in.payment,
        commission=commission,
        commission_pct=pct,
    )


class TripService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- reading a diary ---

    async def days(self, driver_id: int) -> list[DayInfo]:
        async with self._db.unit_of_work() as uow:
            return await uow.trips.days(driver_id)

    async def for_day(self, driver_id: int, day: date) -> list[Trip]:
        async with self._db.unit_of_work() as uow:
            return await uow.trips.for_day(driver_id, day)

    async def day_summary(self, driver_id: int, day: date) -> DaySummary:
        async with self._db.unit_of_work() as uow:
            trips = await uow.trips.for_day(driver_id, day)
            shifts = len(await uow.shifts.for_day(driver_id, day))
        return DaySummary.for_day(day, shifts, trips)

    # --- changes ---

    async def add(self, driver_id: int, trip_in: TripIn, *, by_admin: bool = False) -> tuple[Trip, bool]:
        """Idempotent insert into one of the driver's shifts. Returns (trip, created).

        The same trip sent again returns the stored one (created=False); a different
        trip under an existing id raises TripConflictError.
        """
        async with self._db.unit_of_work() as uow:
            # FOR UPDATE: a concurrent close of this shift waits, so the trip cannot end up
            # outside a shift that was closed meanwhile
            shift = await uow.shifts.get(driver_id, trip_in.shift_id, for_update=True)
            _check_fits_shift(trip_in, shift, by_admin)
            pct = await uow.drivers.commission_pct(driver_id)
            commission = Commission.resolve(trip_in, pct)
            # Remember the percent: editing the amount later recomputes with this one
            trip = _build(driver_id, trip_in, trip_in.id or trip_in.fingerprint(), commission, pct)
            await _check_no_overlap(uow, trip)
            if await uow.trips.insert_if_absent(trip):
                return trip, True
            existing = await uow.trips.get(driver_id, trip.id)
        assert existing is not None  # noqa: S101 - the insert conflicted on this very id
        if existing.same_content(trip):
            return existing, False
        raise TripConflictError(existing)

    async def update(
        self, driver_id: int, trip_id: str, changes: Mapping[str, Any], *, by_admin: bool = False
    ) -> Trip:
        """Apply `changes` (only the fields the client sent) under the same rules as adding.

        The commission follows the percent stored with the trip: a new amount recomputes it,
        and a commission the client sends must match. A trip entered without a percent keeps
        a hand-entered commission, which must stay below the amount.
        """
        async with self._db.unit_of_work() as uow:
            current = await uow.trips.get(driver_id, trip_id)
            if current is None:
                raise NotFoundError()
            # Shifts are locked before the trip, in id order, the same order adding a trip
            # and changing a shift use, so concurrent requests wait instead of deadlocking
            target_id: int = changes.get("shift_id", current.shift_id)
            shifts = {
                i: await uow.shifts.get(driver_id, i, for_update=True)
                for i in sorted({current.shift_id, target_id})
            }
            current = await uow.trips.get(driver_id, trip_id, for_update=True)
            if current is None:
                raise NotFoundError()
            own_shift = shifts.get(current.shift_id)
            if own_shift is None:
                raise ConflictError(ErrorCode.TRIP_CHANGED, "The trip was moved meanwhile, try again")
            if not by_admin:
                ShiftPolicy.editable_by_driver(own_shift)

            merged: dict[str, Any] = {
                "id": current.id,
                "shift_id": current.shift_id,
                "start": current.start,
                "end": current.end,
                "amount": current.amount,
                "payment": current.payment,
                "commission": current.commission,
                **changes,
            }
            if "commission" not in changes and current.commission_pct is not None:
                merged["commission"] = None  # recomputed below
            trip_in = _validated(merged)
            _check_fits_shift(trip_in, shifts[target_id], by_admin)
            commission = Commission.resolve(trip_in, current.commission_pct)
            trip = _build(driver_id, trip_in, current.id, commission, current.commission_pct)
            await _check_no_overlap(uow, trip)
            await uow.trips.update(trip)
            return trip

    async def delete(self, driver_id: int, trip_id: str, *, by_admin: bool = False) -> None:
        async with self._db.unit_of_work() as uow:
            current = await uow.trips.get(driver_id, trip_id)
            if current is None:
                raise NotFoundError()
            shift = await uow.shifts.get(driver_id, current.shift_id, for_update=True)
            if shift is None:
                raise NotFoundError()
            if not by_admin:
                ShiftPolicy.editable_by_driver(shift)
            await uow.trips.delete(driver_id, trip_id)
