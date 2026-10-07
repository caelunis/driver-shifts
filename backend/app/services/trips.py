from datetime import date

from psycopg_pool import ConnectionPool

from app.core.errors import TripConflict
from app.repositories import drivers as drivers_repo
from app.repositories import trips as trips_repo
from app.schemas.trips import DayInfo, DaySummary, Trip, TripIn
from app.services.commission import resolve_commission
from app.services.summary import summarize


def days(pool: ConnectionPool, driver_id: int) -> list[DayInfo]:
    with pool.connection() as conn:
        return trips_repo.days(conn, driver_id)


def for_day(pool: ConnectionPool, driver_id: int, day: date) -> list[Trip]:
    with pool.connection() as conn:
        return trips_repo.for_day(conn, driver_id, day)


def day_summary(pool: ConnectionPool, driver_id: int, day: date) -> DaySummary:
    return summarize(for_day(pool, driver_id, day), day)


def add(pool: ConnectionPool, driver_id: int, trip_in: TripIn) -> tuple[Trip, bool]:
    """Idempotent insert. Returns (trip, created).

    The same trip sent again returns the stored one (created=False); a different
    trip under an existing id raises TripConflict.
    """
    with pool.connection() as conn:
        pct = drivers_repo.commission_pct(conn, driver_id)
        trip = resolve_commission(trip_in, pct).to_trip()
        if trips_repo.insert_if_absent(conn, driver_id, trip):
            return trip, True
        existing = trips_repo.get(conn, driver_id, trip.id)
    if existing.same_content(trip):
        return existing, False
    raise TripConflict(existing)
