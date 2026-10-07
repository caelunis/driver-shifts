from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from psycopg_pool import ConnectionPool

from app.api.deps import get_pool, require_driver
from app.core.errors import TripConflict
from app.schemas.trips import DayInfo, DaySummary, Trip, TripIn
from app.services import trips

router = APIRouter(prefix="/api")


@router.get("/days", response_model=list[DayInfo])
def list_days(pool: ConnectionPool = Depends(get_pool), driver_id: int = Depends(require_driver)):
    return trips.days(pool, driver_id)


@router.get("/trips", response_model=list[Trip])
def list_trips(date: date, pool: ConnectionPool = Depends(get_pool),
               driver_id: int = Depends(require_driver)):
    return trips.for_day(pool, driver_id, date)


@router.get("/summary", response_model=DaySummary)
def day_summary(date: date, pool: ConnectionPool = Depends(get_pool),
                driver_id: int = Depends(require_driver)):
    return trips.day_summary(pool, driver_id, date)


@router.post("/trips", response_model=Trip, status_code=status.HTTP_201_CREATED)
def add_trip(trip_in: TripIn, response: Response, pool: ConnectionPool = Depends(get_pool),
             driver_id: int = Depends(require_driver)):
    try:
        trip, created = trips.add(pool, driver_id, trip_in)
    except TripConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Trip with id={e.existing.id} already exists with different data",
                "existing": e.existing.model_dump(mode="json"),
            },
        )
    if not created:
        response.status_code = status.HTTP_200_OK
    return trip
