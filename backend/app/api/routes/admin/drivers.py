from datetime import date

from fastapi import APIRouter, Depends, Response, status
from psycopg_pool import ConnectionPool

from app.api.deps import get_pool, require_admin
from app.core.errors import Conflict, EmailTaken, NotFound, PlateTaken
from app.schemas.accounts import DriverCreate, DriverInfo, DriverUpdate
from app.schemas.shifts import Shift, ShiftDetail, ShiftPatch
from app.schemas.trips import DayInfo, DaySummary, Trip, TripPatch
from app.services import accounts, shifts, trips

router = APIRouter(prefix="/api/admin/drivers", dependencies=[Depends(require_admin)])


def existing_driver(driver_id: int, pool: ConnectionPool = Depends(get_pool)) -> DriverInfo:
    """The driver from the path, or 404. Admin accounts have no driver profile and are
    never found here, so an admin cannot be edited or deleted through this API."""
    driver = accounts.get_driver(pool, driver_id)
    if driver is None:
        raise NotFound("driver_not_found", "Driver not found")
    return driver


@router.get("", response_model=list[DriverInfo])
def list_drivers(q: str | None = None, pool: ConnectionPool = Depends(get_pool)):
    return accounts.list_drivers(pool, q)


@router.post("", response_model=DriverInfo, status_code=status.HTTP_201_CREATED)
def create_driver(data: DriverCreate, pool: ConnectionPool = Depends(get_pool)):
    try:
        driver_id = accounts.create_driver(pool, data)
    except EmailTaken:
        raise Conflict("email_taken", "Email is already registered")
    except PlateTaken:
        raise Conflict("plate_taken", "Another driver has this plate number")
    return accounts.get_driver(pool, driver_id)


@router.get("/{driver_id}", response_model=DriverInfo)
def get_driver(driver: DriverInfo = Depends(existing_driver)):
    return driver


@router.patch("/{driver_id}", response_model=DriverInfo)
def update_driver(changes: DriverUpdate, driver: DriverInfo = Depends(existing_driver),
                  pool: ConnectionPool = Depends(get_pool)):
    try:
        return accounts.update_driver(pool, driver.id, changes.model_dump(exclude_unset=True))
    except PlateTaken:
        raise Conflict("plate_taken", "Another driver has this plate number")


@router.delete("/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver(driver: DriverInfo = Depends(existing_driver),
                  pool: ConnectionPool = Depends(get_pool)):
    accounts.delete_driver(pool, driver.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- a driver's diary: read, correct and delete entries, without the 7-day limit ---

@router.get("/{driver_id}/days", response_model=list[DayInfo])
def driver_days(driver: DriverInfo = Depends(existing_driver),
                pool: ConnectionPool = Depends(get_pool)):
    return trips.days(pool, driver.id)


@router.get("/{driver_id}/trips", response_model=list[Trip])
def driver_trips(date: date, driver: DriverInfo = Depends(existing_driver),
                 pool: ConnectionPool = Depends(get_pool)):
    return trips.for_day(pool, driver.id, date)


@router.get("/{driver_id}/summary", response_model=DaySummary)
def driver_summary(date: date, driver: DriverInfo = Depends(existing_driver),
                   pool: ConnectionPool = Depends(get_pool)):
    return trips.day_summary(pool, driver.id, date)


@router.get("/{driver_id}/shifts", response_model=list[Shift])
def driver_shifts(date: date, driver: DriverInfo = Depends(existing_driver),
                  pool: ConnectionPool = Depends(get_pool)):
    return shifts.for_day(pool, driver.id, date)


@router.get("/{driver_id}/shifts/{shift_id}", response_model=ShiftDetail)
def driver_shift(shift_id: int, driver: DriverInfo = Depends(existing_driver),
                 pool: ConnectionPool = Depends(get_pool)):
    return shifts.get(pool, driver.id, shift_id)


@router.patch("/{driver_id}/trips/{trip_id}", response_model=Trip)
def update_driver_trip(trip_id: str, changes: TripPatch,
                       driver: DriverInfo = Depends(existing_driver),
                       pool: ConnectionPool = Depends(get_pool)):
    return trips.update(pool, driver.id, trip_id, changes.model_dump(exclude_unset=True),
                        by_admin=True)


@router.delete("/{driver_id}/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver_trip(trip_id: str, driver: DriverInfo = Depends(existing_driver),
                       pool: ConnectionPool = Depends(get_pool)):
    trips.delete(pool, driver.id, trip_id, by_admin=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{driver_id}/shifts/{shift_id}", response_model=Shift)
def update_driver_shift(shift_id: int, changes: ShiftPatch,
                        driver: DriverInfo = Depends(existing_driver),
                        pool: ConnectionPool = Depends(get_pool)):
    return shifts.update(pool, driver.id, shift_id, changes.model_dump(exclude_unset=True),
                         by_admin=True)


@router.delete("/{driver_id}/shifts/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver_shift(shift_id: int, driver: DriverInfo = Depends(existing_driver),
                        pool: ConnectionPool = Depends(get_pool)):
    shifts.delete(pool, driver.id, shift_id, by_admin=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
