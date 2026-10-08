from datetime import date

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DriverId, TripServiceDep, require_driver
from app.core.enums import ErrorCode
from app.core.errors import ConflictError, TripConflictError
from app.domain.models import DayInfo as DayInfoModel
from app.domain.models import DaySummary as DaySummaryModel
from app.domain.models import Trip as TripModel
from app.schemas.trips import DayInfo, DaySummary, Trip, TripIn, TripPatch

# The role is checked for the whole router: a new endpoint here cannot forget it
router = APIRouter(prefix="/api", tags=["trips"], dependencies=[Depends(require_driver)])


@router.get("/days", response_model=list[DayInfo])
async def list_days(trips: TripServiceDep, driver_id: DriverId) -> list[DayInfoModel]:
    return await trips.days(driver_id)


@router.get("/trips", response_model=list[Trip])
async def list_trips(date: date, trips: TripServiceDep, driver_id: DriverId) -> list[TripModel]:
    return await trips.for_day(driver_id, date)


@router.get("/summary", response_model=DaySummary)
async def day_summary(date: date, trips: TripServiceDep, driver_id: DriverId) -> DaySummaryModel:
    return await trips.day_summary(driver_id, date)


@router.post("/trips", response_model=Trip, status_code=status.HTTP_201_CREATED)
async def add_trip(
    trip_in: TripIn, response: Response, trips: TripServiceDep, driver_id: DriverId
) -> TripModel:
    try:
        trip, created = await trips.add(driver_id, trip_in)
    except TripConflictError as e:
        raise ConflictError(
            ErrorCode.TRIP_CONFLICT,
            f"Trip with id={e.existing.id} already exists with different data",
            existing=Trip.model_validate(e.existing).model_dump(mode="json"),
        ) from e
    if not created:
        response.status_code = status.HTTP_200_OK
    return trip


@router.patch("/trips/{trip_id}", response_model=Trip)
async def update_trip(
    trip_id: str, changes: TripPatch, trips: TripServiceDep, driver_id: DriverId
) -> TripModel:
    return await trips.update(driver_id, trip_id, changes.model_dump(exclude_unset=True))


@router.delete("/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(trip_id: str, trips: TripServiceDep, driver_id: DriverId) -> Response:
    await trips.delete(driver_id, trip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
