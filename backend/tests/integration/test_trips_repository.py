from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg
import pytest

from app.db.database import Database
from app.domain.models import Trip
from app.schemas.trips import TripIn
from app.services.trips import TripService
from tests.factories import create_driver, day_shift

NIGHT = {
    "id": "n1",
    "start": "2026-10-02T02:10:00+05:00",
    "end": "2026-10-02T02:35:00+05:00",
    "amount": 2800,
    "payment": "cash",
    "commission": 420,
}


@pytest.fixture
def night_shift(db, driver_id):
    return day_shift(db, driver_id, "2026-10-02", start="02:00", end="10:00")


def night(shift_id, **changes) -> TripIn:
    return TripIn(**{**NIGHT, "shift_id": shift_id, **changes})


def raw_trip(driver_id: int, trip_in: TripIn, **changes) -> Trip:
    """A domain trip built directly, bypassing the service's checks."""
    data = trip_in.model_dump()
    return Trip(**{**data, "driver_id": driver_id, "commission": data["commission"], **changes})


def insert_directly(db, trip: Trip) -> None:
    async def insert(database: Database) -> None:
        async with database.unit_of_work() as uow:
            await uow.trips.insert_if_absent(trip)

    db.run(insert, db.database)


@pytest.fixture
def trips(db):
    return db.service(TripService)


def test_offset_survives_roundtrip(trips, driver_id, night_shift):
    # timestamptz alone would return 21:10 UTC of October 1
    trips.add(driver_id, night(night_shift))
    assert trips.for_day(driver_id, date(2026, 10, 1)) == []
    [trip] = trips.for_day(driver_id, date(2026, 10, 2))
    assert trip.start.isoformat() == "2026-10-02T02:10:00+05:00"
    assert trip.end.isoformat() == "2026-10-02T02:35:00+05:00"


def test_concurrent_inserts_create_exactly_one_row(trips, driver_id, night_shift):
    trip = night(night_shift)
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda _: trips.add(driver_id, trip), range(8)))
    assert sum(created for _, created in results) == 1
    assert len(trips.for_day(driver_id, date(2026, 10, 2))) == 1


def test_same_id_for_different_drivers_is_not_a_conflict(db, trips, driver_id, night_shift):
    other = create_driver(db, "other@example.com", "horse-battery-9")
    other_shift = day_shift(db, other, "2026-10-02", start="02:00", end="10:00")
    _, created_a = trips.add(driver_id, night(night_shift))
    _, created_b = trips.add(other, night(other_shift, amount=9999))
    assert created_a and created_b
    assert trips.for_day(driver_id, date(2026, 10, 2))[0].amount == 2800
    assert trips.for_day(other, date(2026, 10, 2))[0].amount == 9999


def test_days_aggregate_by_shift_day(db, trips, driver_id, night_shift):
    trips.add(driver_id, night(night_shift))
    third = day_shift(db, driver_id, "2026-10-03", start="09:00", end="11:00")
    trips.add(
        driver_id,
        night(
            third,
            id="n2",
            start="2026-10-03T10:00:00+05:00",
            end="2026-10-03T10:30:00+05:00",
            amount=1000,
            commission=100,
        ),
    )
    days = [(d.date.isoformat(), d.count, d.net) for d in trips.days(driver_id)]
    assert days == [("2026-10-02", 1, 2380), ("2026-10-03", 1, 900)]


def test_database_rejects_commission_equal_to_amount(db, driver_id, night_shift):
    # Bypass model validation: the database constraint is the last line of defence
    trip = raw_trip(driver_id, night(night_shift), commission=NIGHT["amount"])
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_directly(db, trip)


def test_database_rejects_a_trip_in_another_drivers_shift(db, driver_id):
    other = create_driver(db, "other@example.com", "horse-battery-9")
    foreign_shift = day_shift(db, other, "2026-10-02", start="02:00", end="10:00")
    trip = raw_trip(driver_id, night(foreign_shift))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        insert_directly(db, trip)


def test_trips_and_shifts_of_a_deleted_driver_are_gone(db, trips, driver_id, night_shift):
    trips.add(driver_id, night(night_shift))
    with db.connection() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (driver_id,))
        assert conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM shifts").fetchone()["n"] == 0
