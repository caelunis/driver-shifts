"""Shifts: a driver's working periods. Every trip belongs to a shift."""

import logging
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

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
    end = shift.end or clock.now().astimezone(shift.start.tzinfo)
    return ShiftReport(shift=shift, summary=ShiftSummary.for_shift(trips, shift.start, end), trips=trips)


async def _check_holds_trips(uow: UnitOfWork, shift_id: int, start: datetime, end: datetime | None) -> None:
    """Every trip of the shift stays inside [start, end]."""
    first, last = await uow.shifts.trips_span(shift_id)
    if first is not None and start > first:
        raise DomainValidationError(
            "start",
            ErrorCode.AFTER_FIRST_TRIP,
            "The shift cannot start after its first trip",
            first_trip_start=first.isoformat(),
        )
    if last is not None and end is not None and end < last:
        raise DomainValidationError(
            "end",
            ErrorCode.BEFORE_LAST_TRIP,
            "The shift cannot end before its last trip",
            last_trip_end=last.isoformat(),
        )


class ShiftService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def start(
        self,
        driver_id: int,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        note: str = "",
        *,
        by_admin: bool = False,
    ) -> ShiftReport:
        """Start a shift now, at `start_at`, or enter a finished past shift (`start_at` + `end_at`)."""
        async with self._db.unit_of_work() as uow:
            # One change to this driver's shifts at a time: a concurrent start waits here
            # and then sees the open shift, instead of racing it into a deadlock
            await uow.drivers.lock(driver_id)
            if start_at is None:
                profile = await uow.drivers.profile(driver_id)
                if profile is None or profile.default_tz is None:
                    raise NotFoundError()
                start_at = clock.now().astimezone(zone(profile.default_tz))
            ShiftPolicy.not_in_future("start", start_at)
            if not by_admin:
                ShiftPolicy.within_window("start", start_at)
            if end_at is not None:
                ShiftPolicy.valid_end(start_at, end_at)
            elif await uow.shifts.get_open(driver_id):
                raise ConflictError(ErrorCode.SHIFT_ALREADY_OPEN, "Close the open shift first")
            try:
                async with uow.conn.transaction():
                    shift = await uow.shifts.insert(driver_id, start_at, end_at, note)
            except (ExclusionViolation, UniqueViolation) as e:
                # An overlap with an existing shift; a concurrent start is already serialized above
                raise ConflictError(ErrorCode.SHIFT_OVERLAP, "Overlaps another shift of this driver") from e
        log.info(
            "shift_started",
            extra={
                "driver_id": driver_id,
                "shift_id": shift.id,
                "past": end_at is not None,
                "by_admin": by_admin,
            },
        )
        return _report(shift, [])

    async def close(self, driver_id: int, shift_id: int, end_at: datetime | None = None) -> ShiftReport:
        """Close an open shift. Allowed however long ago it started: the end time is checked
        against the 24-hour limit instead, so a forgotten shift can always be closed."""
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get(driver_id, shift_id, for_update=True)
            if shift is None:
                raise NotFoundError()
            if shift.end is not None:
                raise ConflictError(ErrorCode.SHIFT_ALREADY_CLOSED, "The shift is already closed")
            if end_at is None:
                end_at = clock.now().astimezone(shift.start.tzinfo)
            ShiftPolicy.valid_end(shift.start, end_at)
            await _check_holds_trips(uow, shift_id, shift.start, end_at)
            closed = await uow.shifts.update(shift_id, shift.start, end_at, shift.note)
            report = _report(closed, await uow.trips.for_shifts([shift_id]))
        log.info("shift_closed", extra={"driver_id": driver_id, "shift_id": shift_id})
        return report

    async def update(
        self, driver_id: int, shift_id: int, changes: Mapping[str, Any], *, by_admin: bool = False
    ) -> ShiftReport:
        """Change start, end or note. `changes` holds only the fields the client sent;
        `end: None` reopens the shift."""
        async with self._db.unit_of_work() as uow:
            await uow.drivers.lock(driver_id)  # driver first, then the shift: the order start() uses
            shift = await uow.shifts.get(driver_id, shift_id, for_update=True)
            if shift is None:
                raise NotFoundError()
            if not by_admin:
                ShiftPolicy.editable_by_driver(shift)
            start_at: datetime = changes.get("start", shift.start)
            end_at: datetime | None = changes.get("end", shift.end)  # an explicit None reopens
            note: str = changes.get("note", shift.note)

            if "start" in changes:
                ShiftPolicy.not_in_future("start", start_at)
                if not by_admin:
                    ShiftPolicy.within_window("start", start_at)
            if end_at is not None:
                if "start" in changes or "end" in changes:
                    ShiftPolicy.valid_end(start_at, end_at)
            elif shift.end is not None or "start" in changes:
                # Reopening, or moving an open shift's start back: it would already be longer
                # than 24 hours. A forgotten open shift is left alone: it can still be closed.
                ShiftPolicy.not_longer_than_max("start" if "start" in changes else "end", start_at)
            await _check_holds_trips(uow, shift_id, start_at, end_at)
            if end_at is None and shift.end is not None and await uow.shifts.get_open(driver_id):
                raise ConflictError(ErrorCode.SHIFT_ALREADY_OPEN, "Close the open shift first")

            try:
                async with uow.conn.transaction():
                    updated = await uow.shifts.update(shift_id, start_at, end_at, note)
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
                "reopened": end_at is None and shift.end is not None,
                "by_admin": by_admin,
            },
        )
        return report

    async def delete(self, driver_id: int, shift_id: int, *, by_admin: bool = False) -> None:
        """Delete the shift together with its trips."""
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get(driver_id, shift_id, for_update=True)
            if shift is None:
                raise NotFoundError()
            if not by_admin:
                ShiftPolicy.editable_by_driver(shift)
            await uow.shifts.delete(shift_id)
        log.info("shift_deleted", extra={"driver_id": driver_id, "shift_id": shift_id, "by_admin": by_admin})

    async def get(self, driver_id: int, shift_id: int) -> ShiftReport:
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get(driver_id, shift_id)
            if shift is None:
                raise NotFoundError()
            return _report(shift, await uow.trips.for_shifts([shift_id]))

    async def current(self, driver_id: int) -> ShiftReport | None:
        async with self._db.unit_of_work() as uow:
            shift = await uow.shifts.get_open(driver_id)
            if shift is None:
                return None
            return _report(shift, await uow.trips.for_shifts([shift.id]))

    async def for_day(self, driver_id: int, day: date) -> list[ShiftReport]:
        async with self._db.unit_of_work() as uow:
            shifts = await uow.shifts.for_day(driver_id, day)
            trips = await uow.trips.for_shifts([s.id for s in shifts])
        by_shift: dict[int, list[Trip]] = {}
        for t in trips:
            by_shift.setdefault(t.shift_id, []).append(t)
        return [_report(s, by_shift.get(s.id, [])) for s in shifts]
