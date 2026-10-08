import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.trips import TripIn
from app.services.trips import TripService
from tests.api import fields, sid, tid
from tests.factories import day_shift

# shift_id 1: the day shift created by the `client` fixture
T1 = {
    "id": tid("t1"),
    "shift_id": sid(1),
    "started_at": "2026-10-01T08:10:00+05:00",
    "ended_at": "2026-10-01T08:32:00+05:00",
    "fare": 2400,
    "payment_method": "card",
    "commission_amount": 360,
}
T2 = {
    "id": tid("t2"),
    "shift_id": sid(1),
    "started_at": "2026-10-01T09:05:00+05:00",
    "ended_at": "2026-10-01T09:20:00+05:00",
    "fare": 1500,
    "payment_method": "cash",
    "commission_amount": 225,
}


@pytest.fixture
def client(db, driver_id):
    """Logged-in client of the conftest driver, who already has trips T1 and T2."""
    assert day_shift(db, driver_id) == sid(1)
    for t in (T1, T2):
        db.service(TripService).add(driver_id, TripIn(**t))
    c = TestClient(create_app(db.database))
    r = c.post("/api/v1/auth/login", json={"email": "driver@example.com", "password": "horse-battery-9"})
    assert r.status_code == 200
    return c


def stored_count(db):
    with db.connection() as conn:
        return conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"]


def count_trips(client, day="2026-10-01"):
    return len(client.get("/api/v1/trips", params={"work_date": day}).json())


# --- reading ---


def test_health(db):
    assert TestClient(create_app(db.database)).get("/api/health").json() == {"status": "ok"}


def test_list_trips_and_summary(client):
    trips = client.get("/api/v1/trips", params={"work_date": "2026-10-01"}).json()
    assert [t["id"] for t in trips] == [tid("t1"), tid("t2")]

    s = client.get("/api/v1/summary", params={"work_date": "2026-10-01"}).json()
    assert s["trips_count"] == 2 and s["revenue"] == 3900 and s["net_income"] == 3315
    assert s["cash"] == {"trips_count": 1, "amount": 1500}


def test_days(client):
    assert client.get("/api/v1/days").json() == [
        {"work_date": "2026-10-01", "trips_count": 2, "net_income": 3315}
    ]


def test_bad_date_param(client):
    assert client.get("/api/v1/trips", params={"work_date": "вчера"}).status_code == 422


# --- adding and duplicate protection ---

NEW = {
    "id": tid("t3"),
    "shift_id": sid(1),
    "started_at": "2026-10-01T10:00:00+05:00",
    "ended_at": "2026-10-01T10:20:00+05:00",
    "fare": 2000,
    "payment_method": "cash",
    "commission_amount": 300,
}


def test_add_trip_created(client, db):
    r = client.post("/api/v1/trips", json=NEW)
    assert r.status_code == 201
    assert count_trips(client) == 3
    assert stored_count(db) == 3  # actually persisted


def test_repeat_same_trip_does_not_duplicate(client):
    assert client.post("/api/v1/trips", json=NEW).status_code == 201
    r = client.post("/api/v1/trips", json=NEW)
    assert r.status_code == 200
    assert r.json()["id"] == tid("t3")
    assert count_trips(client) == 3


def test_repeat_with_different_offset_is_same_trip(client):
    client.post("/api/v1/trips", json=NEW)
    same_in_utc = {**NEW, "started_at": "2026-10-01T05:00:00Z", "ended_at": "2026-10-01T05:20:00Z"}
    assert client.post("/api/v1/trips", json=same_in_utc).status_code == 200
    assert count_trips(client) == 3


def test_same_id_different_data_is_conflict(client):
    r = client.post("/api/v1/trips", json={**T1, "fare": 9999})
    assert r.status_code == 409
    assert count_trips(client) == 2


def test_repeat_without_id_does_not_duplicate(client):
    no_id = {k: v for k, v in NEW.items() if k != "id"}
    r1 = client.post("/api/v1/trips", json=no_id)
    r2 = client.post("/api/v1/trips", json=no_id)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"]
    assert count_trips(client) == 3


# --- validation ---


@pytest.mark.parametrize(
    "patch",
    [
        {"fare": 0},
        {"fare": -100},
        {"ended_at": NEW["started_at"]},  # end == start
        {"ended_at": "2026-10-01T09:59:00+05:00"},  # end before start
        {"commission_amount": 2001},  # commission above amount
        {"commission_amount": 2000},  # commission equal to amount
        {"commission_amount": -1},
        {"payment_method": "crypto"},
        {"started_at": "2026-10-01T10:00:00", "ended_at": "2026-10-01T10:20:00"},  # no timezone offset
    ],
)
def test_invalid_trip_rejected(client, db, patch):
    r = client.post("/api/v1/trips", json={**NEW, **patch})
    assert r.status_code == 422
    assert stored_count(db) == 2


def test_all_field_errors_reported_at_once(client):
    bad = {
        **NEW,
        "ended_at": "2026-10-01T09:00:00+05:00",
        "commission_amount": 5000,
        "payment_method": "crypto",
    }
    r = client.post("/api/v1/trips", json=bad)
    assert r.status_code == 422
    assert fields(r) == {
        "ended_at": "end_before_start",
        "commission_amount": "commission_exceeds_fare",
        "payment_method": "enum",
    }


def test_missing_timezone_error_type(client):
    r = client.post("/api/v1/trips", json={**NEW, "started_at": "2026-10-01T10:00:00"})
    assert r.status_code == 422
    assert fields(r)["started_at"] == "timezone_required"


def test_commission_just_below_amount_is_accepted(client):
    r = client.post("/api/v1/trips", json={**NEW, "commission_amount": NEW["fare"] - 1})
    assert r.status_code == 201


def test_legacy_trip_with_commission_equal_to_amount_is_still_readable(client, db):
    # Rows saved before "commission < amount" was enforced must not break the day view
    with db.connection() as conn:
        conn.execute("ALTER TABLE trips DROP CONSTRAINT trips_commission_below_fare")
        conn.execute(
            "INSERT INTO trips (driver_id, id, started_at, ended_at, started_at_offset_minutes,"
            " ended_at_offset_minutes, fare, payment_method, commission_amount, shift_id)"
            " SELECT driver_id, %s, started_at + interval '3 hours', ended_at + interval '3 hours',"
            " started_at_offset_minutes, ended_at_offset_minutes, 1000, payment_method, 1000, shift_id"
            " FROM trips WHERE id = %s",
            (tid("legacy"), tid("t1")),
        )
        conn.execute(
            "ALTER TABLE trips ADD CONSTRAINT trips_commission_below_fare"
            " CHECK (commission_amount >= 0 AND commission_amount < fare) NOT VALID"
        )
    r = client.get("/api/v1/trips", params={"work_date": "2026-10-01"})
    assert r.status_code == 200
    assert {t["id"] for t in r.json()} == {tid("t1"), tid("t2"), tid("legacy")}
    assert client.get("/api/v1/summary", params={"work_date": "2026-10-01"}).json()["trips_count"] == 3
