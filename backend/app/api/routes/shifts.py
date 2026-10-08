from datetime import date

from fastapi import APIRouter, Depends, Response, status
from psycopg_pool import ConnectionPool

from app.api.deps import get_pool, require_driver
from app.schemas.shifts import Shift, ShiftCloseIn, ShiftDetail, ShiftPatch, ShiftStartIn
from app.services import shifts

router = APIRouter(prefix="/api/shifts")


@router.get("", response_model=list[Shift])
def list_shifts(
    date: date, pool: ConnectionPool = Depends(get_pool), driver_id: int = Depends(require_driver)
):
    """Shifts that started on this local day, each with its summary."""
    return shifts.for_day(pool, driver_id, date)


@router.get("/current", response_model=Shift | None)
def current_shift(pool: ConnectionPool = Depends(get_pool), driver_id: int = Depends(require_driver)):
    """The open shift, or null."""
    return shifts.current(pool, driver_id)


@router.post("", response_model=Shift, status_code=status.HTTP_201_CREATED)
def start_shift(
    data: ShiftStartIn, pool: ConnectionPool = Depends(get_pool), driver_id: int = Depends(require_driver)
):
    return shifts.start(pool, driver_id, data.start, data.end, data.note)


@router.get("/{shift_id}", response_model=ShiftDetail)
def get_shift(
    shift_id: int, pool: ConnectionPool = Depends(get_pool), driver_id: int = Depends(require_driver)
):
    return shifts.get(pool, driver_id, shift_id)


@router.post("/{shift_id}/close", response_model=Shift)
def close_shift(
    shift_id: int,
    data: ShiftCloseIn,
    pool: ConnectionPool = Depends(get_pool),
    driver_id: int = Depends(require_driver),
):
    return shifts.close(pool, driver_id, shift_id, data.end)


@router.patch("/{shift_id}", response_model=Shift)
def update_shift(
    shift_id: int,
    changes: ShiftPatch,
    pool: ConnectionPool = Depends(get_pool),
    driver_id: int = Depends(require_driver),
):
    return shifts.update(pool, driver_id, shift_id, changes.model_dump(exclude_unset=True))


@router.delete("/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift(
    shift_id: int, pool: ConnectionPool = Depends(get_pool), driver_id: int = Depends(require_driver)
):
    """Deletes the shift together with its trips."""
    shifts.delete(pool, driver_id, shift_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
