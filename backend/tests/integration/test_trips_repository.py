from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg
import pytest

from app.repositories import trips as trips_repo
from app.schemas.trips import TripIn
from app.services import trips
from tests.factories import create_driver

NIGHT = {"id": "n1", "start": "2026-10-02T02:10:00+05:00", "end": "2026-10-02T02:35:00+05:00",
         "amount": 2800, "payment": "cash", "commission": 420}


def test_offset_and_local_day_survive_roundtrip(db, driver_id):
    # timestamptz alone would return 21:10 UTC of October 1 and lose the trip's day
    trips.add(db, driver_id, TripIn(**NIGHT))
    assert trips.for_day(db, driver_id, date(2026, 10, 1)) == []
    [trip] = trips.for_day(db, driver_id, date(2026, 10, 2))
    assert trip.start.isoformat() == "2026-10-02T02:10:00+05:00"
    assert trip.end.isoformat() == "2026-10-02T02:35:00+05:00"


def test_concurrent_inserts_create_exactly_one_row(db, driver_id):
    trip = TripIn(**NIGHT)
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda _: trips.add(db, driver_id, trip), range(8)))
    assert sum(created for _, created in results) == 1
    assert len(trips.for_day(db, driver_id, date(2026, 10, 2))) == 1


def test_same_id_for_different_drivers_is_not_a_conflict(db, driver_id):
    other = create_driver(db, "other@example.com", "password123")
    _, created_a = trips.add(db, driver_id, TripIn(**NIGHT))
    _, created_b = trips.add(db, other, TripIn(**{**NIGHT, "amount": 9999}))
    assert created_a and created_b
    assert trips.for_day(db, driver_id, date(2026, 10, 2))[0].amount == 2800
    assert trips.for_day(db, other, date(2026, 10, 2))[0].amount == 9999


def test_days_aggregates_per_day(db, driver_id):
    trips.add(db, driver_id, TripIn(**NIGHT))
    trips.add(db, driver_id, TripIn(**{**NIGHT, "id": "n2", "start": "2026-10-03T10:00:00+05:00",
                                       "end": "2026-10-03T10:30:00+05:00", "amount": 1000,
                                       "commission": 100}))
    days = [(d.date.isoformat(), d.count, d.net) for d in trips.days(db, driver_id)]
    assert days == [("2026-10-02", 1, 2380), ("2026-10-03", 1, 900)]


def test_database_rejects_commission_equal_to_amount(db, driver_id):
    # Bypass model validation: the database constraint is the last line of defence
    trip = TripIn(**NIGHT).to_trip().model_copy(update={"commission": NIGHT["amount"]})
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connection() as conn:
            trips_repo.insert_if_absent(conn, driver_id, trip)


def test_trips_of_a_deleted_driver_are_gone(db, driver_id):
    trips.add(db, driver_id, TripIn(**NIGHT))
    with db.connection() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (driver_id,))
        assert conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"] == 0
