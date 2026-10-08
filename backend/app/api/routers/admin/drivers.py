from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import AccountServiceDep, Authenticated, ShiftServiceDep, TripServiceDep, require_admin
from app.core.constants import API_V1
from app.core.enums import ErrorCode
from app.core.errors import ConflictError, EmailTakenError, NotFoundError, PlateTakenError
from app.domain.models import DayInfo as DayInfoModel
from app.domain.models import DaySummary as DaySummaryModel
from app.domain.models import DriverOverview, ShiftReport
from app.domain.models import Trip as TripModel
from app.schemas.accounts import DriverCreate, DriverInfo, DriverUpdate
from app.schemas.errors import responses
from app.schemas.shifts import Shift, ShiftDetail, ShiftPatch
from app.schemas.trips import DayInfo, DaySummary, Trip, TripPatch

router = APIRouter(
    prefix=f"{API_V1}/admin/drivers",
    tags=["admin"],
    dependencies=[Authenticated, Depends(require_admin)],
    responses=responses(401, 403, 404, 422, 429),
)

WorkDate = Annotated[date, Query(description="A local date: the shifts that started on it")]


async def existing_driver(driver_id: UUID, accounts: AccountServiceDep) -> DriverOverview:
    """The driver from the path, or 404. Admin accounts have no driver profile and are
    never found here, so an admin cannot be edited or deleted through this API."""
    driver = await accounts.get_driver(driver_id)
    if driver is None:
        raise NotFoundError(ErrorCode.DRIVER_NOT_FOUND, "Driver not found")
    return driver


Driver = Annotated[DriverOverview, Depends(existing_driver)]


@router.get("", response_model=list[DriverInfo], summary="Drivers with their totals")
async def list_drivers(
    accounts: AccountServiceDep,
    q: Annotated[str | None, Query(description="Search by name, email, car model or plate")] = None,
) -> list[DriverOverview]:
    return await accounts.list_drivers(q)


@router.post(
    "",
    response_model=DriverInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create a driver",
    responses=responses(409),
)
async def create_driver(data: DriverCreate, accounts: AccountServiceDep) -> DriverOverview:
    try:
        return await accounts.create_driver(data)
    except EmailTakenError as e:
        raise ConflictError(ErrorCode.EMAIL_TAKEN, "Email is already registered") from e
    except PlateTakenError as e:
        raise ConflictError(ErrorCode.PLATE_TAKEN, "Another driver has this plate number") from e


@router.get("/{driver_id}", response_model=DriverInfo, summary="A driver")
async def get_driver(driver: Driver) -> DriverOverview:
    return driver


@router.patch("/{driver_id}", response_model=DriverInfo, summary="Change a driver", responses=responses(409))
async def update_driver(changes: DriverUpdate, driver: Driver, accounts: AccountServiceDep) -> DriverOverview:
    try:
        return await accounts.update_driver(driver.id, changes.model_dump(exclude_unset=True))
    except PlateTakenError as e:
        raise ConflictError(ErrorCode.PLATE_TAKEN, "Another driver has this plate number") from e


@router.delete(
    "/{driver_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a driver with all their data"
)
async def delete_driver(driver: Driver, accounts: AccountServiceDep) -> Response:
    await accounts.delete_driver(driver.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- a driver's diary: read, correct and delete entries, without the 7-day limit ---


@router.get("/{driver_id}/days", response_model=list[DayInfo], summary="The driver's dates with shifts")
async def driver_days(driver: Driver, trips: TripServiceDep) -> list[DayInfoModel]:
    return await trips.days(driver.id)


@router.get("/{driver_id}/trips", response_model=list[Trip], summary="The driver's trips of a date")
async def driver_trips(work_date: WorkDate, driver: Driver, trips: TripServiceDep) -> list[TripModel]:
    return await trips.for_day(driver.id, work_date)


@router.get("/{driver_id}/summary", response_model=DaySummary, summary="The driver's totals of a date")
async def driver_summary(work_date: WorkDate, driver: Driver, trips: TripServiceDep) -> DaySummaryModel:
    return await trips.day_summary(driver.id, work_date)


@router.get("/{driver_id}/shifts", response_model=list[Shift], summary="The driver's shifts of a date")
async def driver_shifts(work_date: WorkDate, driver: Driver, shifts: ShiftServiceDep) -> list[ShiftReport]:
    return await shifts.for_day(driver.id, work_date)


@router.get("/{driver_id}/shifts/{shift_id}", response_model=ShiftDetail, summary="A shift of the driver")
async def driver_shift(shift_id: UUID, driver: Driver, shifts: ShiftServiceDep) -> ShiftReport:
    return await shifts.get(driver.id, shift_id)


@router.patch(
    "/{driver_id}/trips/{trip_id}",
    response_model=Trip,
    summary="Correct a trip, without the 7-day limit",
    responses=responses(409),
)
async def update_driver_trip(
    trip_id: UUID, changes: TripPatch, driver: Driver, trips: TripServiceDep
) -> TripModel:
    return await trips.update(driver.id, trip_id, changes.model_dump(exclude_unset=True), by_admin=True)


@router.delete(
    "/{driver_id}/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a trip"
)
async def delete_driver_trip(trip_id: UUID, driver: Driver, trips: TripServiceDep) -> Response:
    await trips.delete(driver.id, trip_id, by_admin=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{driver_id}/shifts/{shift_id}",
    response_model=Shift,
    summary="Correct a shift, without the 7-day limit",
    responses=responses(409),
)
async def update_driver_shift(
    shift_id: UUID, changes: ShiftPatch, driver: Driver, shifts: ShiftServiceDep
) -> ShiftReport:
    return await shifts.update(driver.id, shift_id, changes.model_dump(exclude_unset=True), by_admin=True)


@router.delete(
    "/{driver_id}/shifts/{shift_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shift and its trips",
)
async def delete_driver_shift(shift_id: UUID, driver: Driver, shifts: ShiftServiceDep) -> Response:
    await shifts.delete(driver.id, shift_id, by_admin=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
