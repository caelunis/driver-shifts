from concurrent.futures import ThreadPoolExecutor
from datetime import date

from app.accounts import create_driver
from app.models import TripIn

NIGHT = {"id": "n1", "start": "2026-10-02T02:10:00+05:00", "end": "2026-10-02T02:35:00+05:00",
         "amount": 2800, "payment": "cash", "commission": 420}


def test_offset_and_local_day_survive_roundtrip(storage, driver_id):
    # timestamptz alone would return 21:10 UTC of October 1 and lose the trip's day
    storage.add(driver_id, TripIn(**NIGHT).to_trip())
    assert storage.for_day(driver_id, date(2026, 10, 1)) == []
    [trip] = storage.for_day(driver_id, date(2026, 10, 2))
    assert trip.start.isoformat() == "2026-10-02T02:10:00+05:00"
    assert trip.end.isoformat() == "2026-10-02T02:35:00+05:00"


def test_concurrent_inserts_create_exactly_one_row(storage, driver_id):
    trip = TripIn(**NIGHT).to_trip()
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda _: storage.add(driver_id, trip), range(8)))
    assert sum(created for _, created in results) == 1
    assert len(storage.for_day(driver_id, date(2026, 10, 2))) == 1


def test_same_id_for_different_drivers_is_not_a_conflict(db, storage, driver_id):
    other = create_driver(db, "other@example.com", "password123")
    _, created_a = storage.add(driver_id, TripIn(**NIGHT).to_trip())
    _, created_b = storage.add(other, TripIn(**{**NIGHT, "amount": 9999}).to_trip())
    assert created_a and created_b
    assert storage.for_day(driver_id, date(2026, 10, 2))[0].amount == 2800
    assert storage.for_day(other, date(2026, 10, 2))[0].amount == 9999


def test_days_aggregates_per_day(storage, driver_id):
    storage.add(driver_id, TripIn(**NIGHT).to_trip())
    storage.add(driver_id, TripIn(**{**NIGHT, "id": "n2", "start": "2026-10-03T10:00:00+05:00",
                                     "end": "2026-10-03T10:30:00+05:00", "amount": 1000,
                                     "commission": 100}).to_trip())
    days = [(d.date.isoformat(), d.count, d.net) for d in storage.days(driver_id)]
    assert days == [("2026-10-02", 1, 2380), ("2026-10-03", 1, 900)]
