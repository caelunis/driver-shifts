from datetime import date

from fastapi import APIRouter, Response, status

from app.api.deps import DriverId, ShiftServiceDep
from app.domain.models import ShiftReport
from app.schemas.shifts import Shift, ShiftCloseIn, ShiftDetail, ShiftPatch, ShiftStartIn

router = APIRouter(prefix="/api/shifts", tags=["shifts"])


@router.get("", response_model=list[Shift])
async def list_shifts(date: date, shifts: ShiftServiceDep, driver_id: DriverId) -> list[ShiftReport]:
    """Shifts that started on this local day, each with its summary."""
    return await shifts.for_day(driver_id, date)


@router.get("/current", response_model=Shift | None)
async def current_shift(shifts: ShiftServiceDep, driver_id: DriverId) -> ShiftReport | None:
    """The open shift, or null."""
    return await shifts.current(driver_id)


@router.post("", response_model=Shift, status_code=status.HTTP_201_CREATED)
async def start_shift(data: ShiftStartIn, shifts: ShiftServiceDep, driver_id: DriverId) -> ShiftReport:
    return await shifts.start(driver_id, data.start, data.end, data.note)


@router.get("/{shift_id}", response_model=ShiftDetail)
async def get_shift(shift_id: int, shifts: ShiftServiceDep, driver_id: DriverId) -> ShiftReport:
    return await shifts.get(driver_id, shift_id)


@router.post("/{shift_id}/close", response_model=Shift)
async def close_shift(
    shift_id: int, data: ShiftCloseIn, shifts: ShiftServiceDep, driver_id: DriverId
) -> ShiftReport:
    return await shifts.close(driver_id, shift_id, data.end)


@router.patch("/{shift_id}", response_model=Shift)
async def update_shift(
    shift_id: int, changes: ShiftPatch, shifts: ShiftServiceDep, driver_id: DriverId
) -> ShiftReport:
    return await shifts.update(driver_id, shift_id, changes.model_dump(exclude_unset=True))


@router.delete("/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shift(shift_id: int, shifts: ShiftServiceDep, driver_id: DriverId) -> Response:
    """Deletes the shift together with its trips."""
    await shifts.delete(driver_id, shift_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
