from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import Authenticated, DriverId, TripServiceDep, require_driver
from app.core.constants import API_V1
from app.core.enums import ErrorCode
from app.core.errors import ConflictError, TripConflictError
from app.domain.models import DayInfo as DayInfoModel
from app.domain.models import DaySummary as DaySummaryModel
from app.domain.models import Trip as TripModel
from app.schemas.errors import responses
from app.schemas.trips import DayInfo, DaySummary, Trip, TripIn, TripPatch

# The role is checked for the whole router: a new endpoint here cannot forget it
router = APIRouter(
    prefix=API_V1,
    tags=["trips"],
    dependencies=[Authenticated, Depends(require_driver)],
    responses=responses(401, 403, 422, 429),
)

WorkDate = Annotated[date, Query(description="A local date: the shifts that started on it")]


@router.get("/days", response_model=list[DayInfo], summary="Dates with shifts")
async def list_days(trips: TripServiceDep, driver_id: DriverId) -> list[DayInfoModel]:
    """Every work date with at least one shift, with its trip count and take-home: the calendar."""
    return await trips.days(driver_id)


@router.get("/trips", response_model=list[Trip], summary="Trips of a date")
async def list_trips(work_date: WorkDate, trips: TripServiceDep, driver_id: DriverId) -> list[TripModel]:
    """Trips of the shifts that started on `work_date`, a night shift's trips after midnight included."""
    return await trips.for_day(driver_id, work_date)


@router.get("/summary", response_model=DaySummary, summary="Totals of a date")
async def day_summary(work_date: WorkDate, trips: TripServiceDep, driver_id: DriverId) -> DaySummaryModel:
    """Revenue, commission, take-home and the cash/card split of the date's shifts."""
    return await trips.day_summary(driver_id, work_date)


@router.post(
    "/trips",
    response_model=Trip,
    status_code=status.HTTP_201_CREATED,
    summary="Add a trip",
    responses={
        200: {"model": Trip, "description": "The same trip again: the stored one, nothing added"},
        **responses(409),
    },
)
async def add_trip(
    trip_in: TripIn, response: Response, trips: TripServiceDep, driver_id: DriverId
) -> TripModel:
    """Adds a trip to one of the driver's shifts, inside its start and end.

    Idempotent by `id`: a retried request returns **200** with the stored trip. The same `id`
    with different data is **409 trip_conflict**; a time that overlaps another trip is
    **409 trip_overlap**. With a commission percent set by the admin, the server computes
    `commission_amount`. A shift that ended more than 7 days ago no longer takes trips.
    """
    try:
        trip, created = await trips.add(driver_id, trip_in)
    except TripConflictError as e:
        raise ConflictError(
            ErrorCode.TRIP_CONFLICT,
            f"Trip {e.existing.id} already exists with different data",
            existing=Trip.model_validate(e.existing).model_dump(mode="json"),
        ) from e
    if not created:
        response.status_code = status.HTTP_200_OK
    return trip


@router.patch("/trips/{trip_id}", response_model=Trip, summary="Change a trip", responses=responses(404, 409))
async def update_trip(
    trip_id: UUID, changes: TripPatch, trips: TripServiceDep, driver_id: DriverId
) -> TripModel:
    """Only the fields sent change; the same rules as adding apply. A new fare recomputes the
    commission with the percent stored with the trip. 409 shift_locked after 7 days."""
    return await trips.update(driver_id, trip_id, changes.model_dump(exclude_unset=True))


@router.delete(
    "/trips/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trip",
    responses=responses(404, 409),
)
async def delete_trip(trip_id: UUID, trips: TripServiceDep, driver_id: DriverId) -> Response:
    await trips.delete(driver_id, trip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
