"""Trips, and the per-day views of a diary."""

import logging
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.core.enums import ErrorCode
from app.core.errors import ConflictError, DomainValidationError, NotFoundError, TripConflictError
from app.db.database import Database, UnitOfWork
from app.domain.models import DayInfo, DaySummary, Shift, Trip
from app.schemas.trips import TripIn
from app.services.commission import Commission
from app.services.policies import ShiftPolicy

log = logging.getLogger(__name__)


def _check_fits_shift(trip: TripIn, shift: Shift | None, by_admin: bool) -> Shift:
    if shift is None:
        raise DomainValidationError("shift_id", ErrorCode.SHIFT_NOT_FOUND, "No such shift")
    if not by_admin and shift.ended_at is not None:
        # A shift older than the window is locked for the driver
        ShiftPolicy.within_window("shift_id", shift.ended_at)
    if trip.started_at < shift.started_at:
        raise DomainValidationError(
            "started_at",
            ErrorCode.OUTSIDE_SHIFT,
            "The trip starts before the shift",
            shift_started_at=shift.started_at.isoformat(),
        )
    if shift.ended_at is not None and trip.ended_at > shift.ended_at:
        raise DomainValidationError(
            "ended_at",
            ErrorCode.OUTSIDE_SHIFT,
            "The trip ends after the shift",
            shift_ended_at=shift.ended_at.isoformat(),
        )
    ShiftPolicy.not_in_future("ended_at", trip.ended_at)
    return shift


async def _check_no_overlap(uow: UnitOfWork, trip: Trip) -> None:
    # Also enforced by the trips_no_overlap constraint; checked first to name the other trip.
    # The id itself is excluded, so resending the same trip stays idempotent.
    other = await uow.trips.overlapping(trip.driver_id, trip.started_at, trip.ended_at, trip.id)
    if other is not None:
        raise ConflictError(
            ErrorCode.TRIP_OVERLAP, "Overlaps another trip of this driver", trip_id=str(other)
        )


def _validated(data: Mapping[str, Any]) -> TripIn:
    """Re-check a merged trip; reports the first error like a body validation error."""
    try:
        return TripIn.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        raise DomainValidationError(str(err["loc"][0]), err["type"], err["msg"]) from e


def _build(
    driver_id: UUID, trip_in: TripIn, trip_id: UUID, commission_amount: int, percent: Decimal | None
) -> Trip:
    return Trip(
        id=trip_id,
        driver_id=driver_id,
        shift_id=trip_in.shift_id,
        started_at=trip_in.started_at,
        ended_at=trip_in.ended_at,
        fare=trip_in.fare,
        payment_method=trip_in.payment_method,
        commission_amount=commission_amount,
        commission_percent=percent,
    )


class TripService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- reading a diary ---

    async def days(self, driver_id: UUID) -> list[DayInfo]:
        async with self._db.unit_of_work() as uow:
            return await uow.trips.days(driver_id)

    async def for_day(self, driver_id: UUID, work_date: date) -> list[Trip]:
        async with self._db.unit_of_work() as uow:
            return await uow.trips.for_day(driver_id, work_date)

    async def day_summary(self, driver_id: UUID, work_date: date) -> DaySummary:
        async with self._db.unit_of_work() as uow:
            trips = await uow.trips.for_day(driver_id, work_date)
            shifts_count = len(await uow.shifts.for_day(driver_id, work_date))
        return DaySummary.for_day(work_date, shifts_count, trips)

    # --- changes ---

    async def add(self, driver_id: UUID, trip_in: TripIn, *, by_admin: bool = False) -> tuple[Trip, bool]:
        """Idempotent insert into one of the driver's shifts. Returns (trip, created).

        The same trip sent again returns the stored one (created=False); a different
        trip under an existing id raises TripConflictError.
        """
        async with self._db.unit_of_work() as uow:
            # FOR UPDATE: a concurrent close of this shift waits, so the trip cannot end up
            # outside a shift that was closed meanwhile
            shift = await uow.shifts.get(driver_id, trip_in.shift_id, for_update=True)
            _check_fits_shift(trip_in, shift, by_admin)
            percent = await uow.drivers.commission_percent(driver_id)
            commission_amount = Commission.resolve(trip_in, percent)
            # Remember the percent: editing the fare later recomputes with this one
            trip = _build(driver_id, trip_in, trip_in.id or trip_in.content_id(), commission_amount, percent)
            await _check_no_overlap(uow, trip)
            created = await uow.trips.insert_if_absent(trip)
            existing = None if created else await uow.trips.get(driver_id, trip.id)
        ids = {"driver_id": driver_id, "trip_id": trip.id, "shift_id": trip.shift_id, "by_admin": by_admin}
        if created:
            log.info("trip_added", extra=ids)
            return trip, True
        assert existing is not None  # noqa: S101 - the insert conflicted on this very id
        if existing.same_content(trip):
            log.info("trip_duplicate_ignored", extra=ids)  # a retried request: nothing stored twice
            return existing, False
        log.warning("trip_conflict", extra=ids)
        raise TripConflictError(existing)

    async def update(
        self, driver_id: UUID, trip_id: UUID, changes: Mapping[str, Any], *, by_admin: bool = False
    ) -> Trip:
        """Apply `changes` (only the fields the client sent) under the same rules as adding.

        The commission follows the percent stored with the trip: a new fare recomputes it,
        and a commission the client sends must match. A trip entered without a percent keeps
        a hand-entered commission, which must stay below the fare.
        """
        async with self._db.unit_of_work() as uow:
            current = await uow.trips.get(driver_id, trip_id)
            if current is None:
                raise NotFoundError()
            # Shifts are locked before the trip, in id order, the same order adding a trip
            # and changing a shift use, so concurrent requests wait instead of deadlocking
            target_id: UUID = changes.get("shift_id", current.shift_id)
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
                "started_at": current.started_at,
                "ended_at": current.ended_at,
                "fare": current.fare,
                "payment_method": current.payment_method,
                "commission_amount": current.commission_amount,
                **changes,
            }
            if "commission_amount" not in changes and current.commission_percent is not None:
                merged["commission_amount"] = None  # recomputed below
            trip_in = _validated(merged)
            _check_fits_shift(trip_in, shifts[target_id], by_admin)
            commission_amount = Commission.resolve(trip_in, current.commission_percent)
            trip = _build(driver_id, trip_in, current.id, commission_amount, current.commission_percent)
            await _check_no_overlap(uow, trip)
            await uow.trips.update(trip)
        log.info(
            "trip_updated",
            extra={
                "driver_id": driver_id,
                "trip_id": trip_id,
                "fields": sorted(changes),
                "by_admin": by_admin,
            },
        )
        return trip

    async def delete(self, driver_id: UUID, trip_id: UUID, *, by_admin: bool = False) -> None:
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
        log.info("trip_deleted", extra={"driver_id": driver_id, "trip_id": trip_id, "by_admin": by_admin})
