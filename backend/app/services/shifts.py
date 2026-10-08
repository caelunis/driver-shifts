"""Shifts: a driver's working periods. Every trip belongs to a shift."""

import logging
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

from psycopg.errors import ExclusionViolation, UniqueViolation

from app.core import clock
from app.core.enums import ErrorCode
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.db.database import Database, UnitOfWork
from app.domain.models import Shift, ShiftReport, ShiftSummary, Trip
from app.schemas.common import zone
from app.services.policies import ShiftPolicy

log = logging.getLogger(__name__)


def _report(shift: Shift, trips: list[Trip]) -> ShiftReport:
    # An open shift is summarized up to now, in the shift's own offset
    ended_at = shift.ended_at or clock.now().astimezone(shift.started_at.tzinfo)
    summary = ShiftSummary.for_shift(trips, shift.started_at, ended_at)
    return ShiftReport(shift=shift, summary=summary, trips=trips)


async def _check_holds_trips(
    uow: UnitOfWork, shift_id: UUID, started_at: datetime, ended_at: datetime | None
) -> None:
    """Every trip of the shift stays inside [started_at, ended_at]."""
    first, last = await uow.shifts.trips_span(shift_id)
    if first is not None and started_at > first:
        raise DomainValidationError(
            "started_at",
            ErrorCode.AFTER_FIRST_TRIP,
            "The shift cannot start after its first trip",
            first_trip_started_at=first.isoformat(),
        )
    if last is not None and ended_at is not None and ended_at < last:
        raise DomainValidationError(
            "ended_at",
            ErrorCode.BEFORE_LAST_TRIP,
            "The shift cannot end before its last trip",
            last_trip_ended_at=last.isoformat(),
        )


class ShiftService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def start(
        self,
        driver_id: UUID,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        note: str = "",
        *,
        by_admin: bool = False,
    ) -> ShiftReport:
        """Start a shift now, at `started_at`, or enter a finished past shift (with `ended_at`)."""
        async with self._db.unit_of_work() as uow:
            # One change to this driver's shifts at a time: a concurrent start waits here
            # and then sees the open shift, instead of racing it into a deadlock
            await uow.drivers.lock(driver_id)
            if started_at is None:
                profile = await uow.drivers.profile(driver_id)
                if profile is None or profile.timezone is None:
                    raise NotFoundError()
                started_at = clock.now().astimezone(zone(profile.timezone))
            ShiftPolicy.not_in_future("started_at", started_at)
            if not by_admin:
                ShiftPolicy.within_window("started_at", started_at)
            if ended_at is not None:
                ShiftPolicy.valid_end(started_at, ended_at)
            elif await uow.shifts.get_open(driver_id):
                raise ConflictError(ErrorCode.SHIFT_ALREADY_OPEN, "Close the open shift first")
            try:
                async with uow.conn.transaction():
                    shift = await uow.shifts.insert(driver_id, started_at, ended_at, note)
            except (ExclusionViolation, UniqueViolation) as e:
                # An overlap with an existing shift; a concurrent start is already serialized above
                raise ConflictError(ErrorCode.SHIFT_OVERLAP, "Overlaps another shift of this driver") from e
        log.info(
            "shift_started",
            extra={
                "driver_id": driver_id,
                "shift_id": shift.id,
                "past": ended_at is not None,
                "by_admin": by_admin,
            },
        )
        return _report(shift, [])

    async def close(self, driver_id: UUID, shift_id: UUID, ended_at: datetime | None = None) -> ShiftReport:
        """Close an open shift. Allowed however long ago it started: the end time is checked
        against the 24-hour limit instead, so a forgotten shift can always be closed."""
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get(driver_id, shift_id, for_update=True)
            if shift is None:
                raise NotFoundError()
            if shift.ended_at is not None:
                raise ConflictError(ErrorCode.SHIFT_ALREADY_CLOSED, "The shift is already closed")
            if ended_at is None:
                ended_at = clock.now().astimezone(shift.started_at.tzinfo)
            ShiftPolicy.valid_end(shift.started_at, ended_at)
            await _check_holds_trips(uow, shift_id, shift.started_at, ended_at)
            closed = await uow.shifts.update(shift_id, shift.started_at, ended_at, shift.note)
            report = _report(closed, await uow.trips.for_shifts([shift_id]))
        log.info("shift_closed", extra={"driver_id": driver_id, "shift_id": shift_id})
        return report

    async def update(
        self, driver_id: UUID, shift_id: UUID, changes: Mapping[str, Any], *, by_admin: bool = False
    ) -> ShiftReport:
        """Change started_at, ended_at or note. `changes` holds only the fields the client
        sent; `ended_at: None` reopens the shift."""
        async with self._db.unit_of_work() as uow:
            await uow.drivers.lock(driver_id)  # driver first, then the shift: the order start() uses
            shift = await uow.shifts.get(driver_id, shift_id, for_update=True)
            if shift is None:
                raise NotFoundError()
            if not by_admin:
                ShiftPolicy.editable_by_driver(shift)
            started_at: datetime = changes.get("started_at", shift.started_at)
            ended_at: datetime | None = changes.get("ended_at", shift.ended_at)  # explicit None reopens
            note: str = changes.get("note", shift.note)

            if "started_at" in changes:
                ShiftPolicy.not_in_future("started_at", started_at)
                if not by_admin:
                    ShiftPolicy.within_window("started_at", started_at)
            if ended_at is not None:
                if "started_at" in changes or "ended_at" in changes:
                    ShiftPolicy.valid_end(started_at, ended_at)
            elif shift.ended_at is not None or "started_at" in changes:
                # Reopening, or moving an open shift's start back: it would already be longer
                # than 24 hours. A forgotten open shift is left alone: it can still be closed.
                ShiftPolicy.not_longer_than_max(
                    "started_at" if "started_at" in changes else "ended_at", started_at
                )
            await _check_holds_trips(uow, shift_id, started_at, ended_at)
            if ended_at is None and shift.ended_at is not None and await uow.shifts.get_open(driver_id):
                raise ConflictError(ErrorCode.SHIFT_ALREADY_OPEN, "Close the open shift first")

            try:
                async with uow.conn.transaction():
                    updated = await uow.shifts.update(shift_id, started_at, ended_at, note)
            except UniqueViolation as e:
                raise ConflictError(ErrorCode.SHIFT_ALREADY_OPEN, "Close the open shift first") from e
            except ExclusionViolation as e:
                # An open shift extends to infinity, so only the latest shift can be reopened
                raise ConflictError(ErrorCode.SHIFT_OVERLAP, "Overlaps another shift of this driver") from e
            report = _report(updated, await uow.trips.for_shifts([shift_id]))
        log.info(
            "shift_updated",
            extra={
                "driver_id": driver_id,
                "shift_id": shift_id,
                "fields": sorted(changes),
                "reopened": ended_at is None and shift.ended_at is not None,
                "by_admin": by_admin,
            },
        )
        return report

    async def delete(self, driver_id: UUID, shift_id: UUID, *, by_admin: bool = False) -> None:
        """Delete the shift together with its trips."""
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get(driver_id, shift_id, for_update=True)
            if shift is None:
                raise NotFoundError()
            if not by_admin:
                ShiftPolicy.editable_by_driver(shift)
            await uow.shifts.delete(shift_id)
        log.info("shift_deleted", extra={"driver_id": driver_id, "shift_id": shift_id, "by_admin": by_admin})

    async def get(self, driver_id: UUID, shift_id: UUID) -> ShiftReport:
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get(driver_id, shift_id)
            if shift is None:
                raise NotFoundError()
            return _report(shift, await uow.trips.for_shifts([shift_id]))

    async def current(self, driver_id: UUID) -> ShiftReport | None:
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get_open(driver_id)
            if shift is None:
                return None
            return _report(shift, await uow.trips.for_shifts([shift.id]))

    async def for_day(self, driver_id: UUID, work_date: date) -> list[ShiftReport]:
        async with self._db.unit_of_work() as uow:
            shifts = await uow.shifts.for_day(driver_id, work_date)
            trips = await uow.trips.for_shifts([s.id for s in shifts])
        by_shift: dict[UUID, list[Trip]] = {}
        for t in trips:
            by_shift.setdefault(t.shift_id, []).append(t)
        return [_report(s, by_shift.get(s.id, [])) for s in shifts]
