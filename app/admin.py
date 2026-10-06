from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status

from . import accounts
from .deps import get_storage, require_admin
from .models import DayInfo, DaySummary, DriverCreate, DriverInfo, DriverUpdate, Trip
from .storage import TripStorage
from .summary import summarize

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def existing_driver(driver_id: int, storage: TripStorage = Depends(get_storage)) -> DriverInfo:
    """The driver from the path, or 404. Admin accounts are not drivers and are never found
    here, so an admin cannot be edited or deleted through this API (self included)."""
    driver = accounts.get_driver_info(storage.pool, driver_id)
    if driver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found")
    return driver


@router.get("/drivers", response_model=list[DriverInfo])
def list_drivers(q: str | None = None, storage: TripStorage = Depends(get_storage)):
    return accounts.list_drivers(storage.pool, q)


@router.post("/drivers", response_model=DriverInfo, status_code=status.HTTP_201_CREATED)
def create_driver(data: DriverCreate, storage: TripStorage = Depends(get_storage)):
    try:
        driver_id = accounts.create_driver(storage.pool, data.email, data.password, data.name)
    except accounts.EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    accounts.admin_update_driver(storage.pool, driver_id, data.model_dump(
        include={"car", "default_tz", "default_commission_pct"}))
    return accounts.get_driver_info(storage.pool, driver_id)


@router.get("/drivers/{driver_id}", response_model=DriverInfo)
def get_driver(driver: DriverInfo = Depends(existing_driver)):
    return driver


@router.patch("/drivers/{driver_id}", response_model=DriverInfo)
def update_driver(changes: DriverUpdate, driver: DriverInfo = Depends(existing_driver),
                  storage: TripStorage = Depends(get_storage)):
    accounts.admin_update_driver(storage.pool, driver.id, changes.model_dump(exclude_unset=True))
    return accounts.get_driver_info(storage.pool, driver.id)


@router.delete("/drivers/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver(driver: DriverInfo = Depends(existing_driver),
                  storage: TripStorage = Depends(get_storage)):
    accounts.delete_driver(storage.pool, driver.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- read-only view of a driver's diary ---

@router.get("/drivers/{driver_id}/days", response_model=list[DayInfo])
def driver_days(driver: DriverInfo = Depends(existing_driver),
                storage: TripStorage = Depends(get_storage)):
    return storage.days(driver.id)


@router.get("/drivers/{driver_id}/trips", response_model=list[Trip])
def driver_trips(date: date, driver: DriverInfo = Depends(existing_driver),
                 storage: TripStorage = Depends(get_storage)):
    return storage.for_day(driver.id, date)


@router.get("/drivers/{driver_id}/summary", response_model=DaySummary)
def driver_summary(date: date, driver: DriverInfo = Depends(existing_driver),
                   storage: TripStorage = Depends(get_storage)):
    return summarize(storage.for_day(driver.id, date), date)
