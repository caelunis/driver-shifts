import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import TripIn

T1 = {"id": "t1", "start": "2026-10-01T08:10:00+05:00", "end": "2026-10-01T08:32:00+05:00",
      "amount": 2400, "payment": "card", "commission": 360}
T2 = {"id": "t2", "start": "2026-10-01T09:05:00+05:00", "end": "2026-10-01T09:20:00+05:00",
      "amount": 1500, "payment": "cash", "commission": 225}


@pytest.fixture
def client(db, storage, driver_id):
    for t in (T1, T2):
        storage.add(driver_id, TripIn(**t).to_trip())
    return TestClient(create_app(db))


def stored_count(db):
    with db.connection() as conn:
        return conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"]


def count_trips(client, day="2026-10-01"):
    return len(client.get("/api/trips", params={"date": day}).json())


# --- reading ---

def test_list_trips_and_summary(client):
    trips = client.get("/api/trips", params={"date": "2026-10-01"}).json()
    assert [t["id"] for t in trips] == ["t1", "t2"]

    s = client.get("/api/summary", params={"date": "2026-10-01"}).json()
    assert s["count"] == 2 and s["revenue"] == 3900 and s["net"] == 3315
    assert s["cash"] == {"count": 1, "amount": 1500}


def test_days(client):
    assert client.get("/api/days").json() == [{"date": "2026-10-01", "count": 2, "net": 3315}]


def test_bad_date_param(client):
    assert client.get("/api/trips", params={"date": "вчера"}).status_code == 422


# --- adding and duplicate protection ---

NEW = {"id": "t3", "start": "2026-10-01T10:00:00+05:00", "end": "2026-10-01T10:20:00+05:00",
       "amount": 2000, "payment": "cash", "commission": 300}


def test_add_trip_created(client, db):
    r = client.post("/api/trips", json=NEW)
    assert r.status_code == 201
    assert count_trips(client) == 3
    assert stored_count(db) == 3  # actually persisted


def test_repeat_same_trip_does_not_duplicate(client):
    assert client.post("/api/trips", json=NEW).status_code == 201
    r = client.post("/api/trips", json=NEW)
    assert r.status_code == 200
    assert r.json()["id"] == "t3"
    assert count_trips(client) == 3


def test_repeat_with_different_offset_is_same_trip(client):
    client.post("/api/trips", json=NEW)
    same_in_utc = {**NEW, "start": "2026-10-01T05:00:00Z", "end": "2026-10-01T05:20:00Z"}
    assert client.post("/api/trips", json=same_in_utc).status_code == 200
    assert count_trips(client) == 3


def test_same_id_different_data_is_conflict(client):
    r = client.post("/api/trips", json={**T1, "amount": 9999})
    assert r.status_code == 409
    assert count_trips(client) == 2


def test_repeat_without_id_does_not_duplicate(client):
    no_id = {k: v for k, v in NEW.items() if k != "id"}
    r1 = client.post("/api/trips", json=no_id)
    r2 = client.post("/api/trips", json=no_id)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"]
    assert count_trips(client) == 3


# --- validation ---

@pytest.mark.parametrize("patch", [
    {"amount": 0},
    {"amount": -100},
    {"end": NEW["start"]},                       # end == start
    {"end": "2026-10-01T09:59:00+05:00"},        # end before start
    {"commission": 2001},                        # commission above amount
    {"commission": -1},
    {"payment": "crypto"},
    {"start": "2026-10-01T10:00:00", "end": "2026-10-01T10:20:00"},  # no timezone offset
])
def test_invalid_trip_rejected(client, db, patch):
    r = client.post("/api/trips", json={**NEW, **patch})
    assert r.status_code == 422
    assert stored_count(db) == 2


def test_all_field_errors_reported_at_once(client):
    bad = {**NEW, "end": "2026-10-01T09:00:00+05:00", "commission": 5000, "payment": "crypto"}
    r = client.post("/api/trips", json=bad)
    assert r.status_code == 422
    errors = {e["loc"][-1]: e["type"] for e in r.json()["detail"]}
    assert errors == {
        "end": "end_before_start",
        "commission": "commission_exceeds_amount",
        "payment": "literal_error",
    }


def test_missing_timezone_error_type(client):
    r = client.post("/api/trips", json={**NEW, "start": "2026-10-01T10:00:00"})
    assert r.status_code == 422
    assert {e["loc"][-1]: e["type"] for e in r.json()["detail"]}["start"] == "timezone_required"
