from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from psycopg_pool import ConnectionPool

from app.api.deps import get_pool, require_admin
from app.core.errors import EmailTaken
from app.schemas.accounts import DriverCreate, DriverInfo, DriverUpdate
from app.schemas.trips import DayInfo, DaySummary, Trip
from app.services import accounts, trips

router = APIRouter(prefix="/api/admin/drivers", dependencies=[Depends(require_admin)])


def existing_driver(driver_id: int, pool: ConnectionPool = Depends(get_pool)) -> DriverInfo:
    """The driver from the path, or 404. Admin accounts have no driver profile and are
    never found here, so an admin cannot be edited or deleted through this API."""
    driver = accounts.get_driver(pool, driver_id)
    if driver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found")
    return driver


@router.get("", response_model=list[DriverInfo])
def list_drivers(q: str | None = None, pool: ConnectionPool = Depends(get_pool)):
    return accounts.list_drivers(pool, q)


@router.post("", response_model=DriverInfo, status_code=status.HTTP_201_CREATED)
def create_driver(data: DriverCreate, pool: ConnectionPool = Depends(get_pool)):
    try:
        driver_id = accounts.create_driver(pool, data)
    except EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    return accounts.get_driver(pool, driver_id)


@router.get("/{driver_id}", response_model=DriverInfo)
def get_driver(driver: DriverInfo = Depends(existing_driver)):
    return driver


@router.patch("/{driver_id}", response_model=DriverInfo)
def update_driver(changes: DriverUpdate, driver: DriverInfo = Depends(existing_driver),
                  pool: ConnectionPool = Depends(get_pool)):
    return accounts.update_driver(pool, driver.id, changes.model_dump(exclude_unset=True))


@router.delete("/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver(driver: DriverInfo = Depends(existing_driver),
                  pool: ConnectionPool = Depends(get_pool)):
    accounts.delete_driver(pool, driver.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- read-only view of a driver's diary ---

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
