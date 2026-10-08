from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import Authenticated, DriverId, ShiftServiceDep, require_driver
from app.core.constants import API_V1
from app.domain.models import ShiftReport
from app.schemas.errors import responses
from app.schemas.shifts import Shift, ShiftCloseIn, ShiftDetail, ShiftPatch, ShiftStartIn

# The role is checked for the whole router: a new endpoint here cannot forget it
router = APIRouter(
    prefix=f"{API_V1}/shifts",
    tags=["shifts"],
    dependencies=[Authenticated, Depends(require_driver)],
    responses=responses(401, 403, 422, 429),
)


@router.get("", response_model=list[Shift], summary="Shifts of a date")
async def list_shifts(
    work_date: Annotated[date, Query(description="A local date")],
    shifts: ShiftServiceDep,
    driver_id: DriverId,
) -> list[ShiftReport]:
    """Shifts that started on `work_date`, each with its summary."""
    return await shifts.for_day(driver_id, work_date)


@router.get("/current", response_model=Shift | None, summary="The open shift")
async def current_shift(shifts: ShiftServiceDep, driver_id: DriverId) -> ShiftReport | None:
    """The shift that is still open, or null."""
    return await shifts.current(driver_id)


@router.post(
    "",
    response_model=Shift,
    status_code=status.HTTP_201_CREATED,
    summary="Start a shift, or enter a past one",
    responses=responses(409),
)
async def start_shift(data: ShiftStartIn, shifts: ShiftServiceDep, driver_id: DriverId) -> ShiftReport:
    """An empty body starts a shift now. With `started_at` only, a shift starts then; with
    `ended_at` too, a finished past shift is entered.

    At most 24 hours long, at most 7 days back, never in the future. One open shift at a
    time (**409 shift_already_open**); shifts never overlap (**409 shift_overlap**).
    """
    return await shifts.start(driver_id, data.started_at, data.ended_at, data.note)


@router.get(
    "/{shift_id}", response_model=ShiftDetail, summary="A shift with its trips", responses=responses(404)
)
async def get_shift(shift_id: UUID, shifts: ShiftServiceDep, driver_id: DriverId) -> ShiftReport:
    return await shifts.get(driver_id, shift_id)


@router.post(
    "/{shift_id}/close", response_model=Shift, summary="Close the open shift", responses=responses(404, 409)
)
async def close_shift(
    shift_id: UUID, data: ShiftCloseIn, shifts: ShiftServiceDep, driver_id: DriverId
) -> ShiftReport:
    """Ends the shift now or at `ended_at`, not before its last trip. A forgotten shift can
    always be closed, with an end within 24 hours of its start."""
    return await shifts.close(driver_id, shift_id, data.ended_at)


@router.patch("/{shift_id}", response_model=Shift, summary="Change a shift", responses=responses(404, 409))
async def update_shift(
    shift_id: UUID, changes: ShiftPatch, shifts: ShiftServiceDep, driver_id: DriverId
) -> ShiftReport:
    """Only the fields sent change. The trips must stay inside; `ended_at: null` reopens the
    latest shift. 409 shift_locked once it ended more than 7 days ago."""
    return await shifts.update(driver_id, shift_id, changes.model_dump(exclude_unset=True))


@router.delete(
    "/{shift_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shift and its trips",
    responses=responses(404, 409),
)
async def delete_shift(shift_id: UUID, shifts: ShiftServiceDep, driver_id: DriverId) -> Response:
    await shifts.delete(driver_id, shift_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
