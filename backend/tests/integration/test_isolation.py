import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api import tid
from tests.factories import create_driver, day_shift

TRIP = {
    "id": tid("t1"),
    "started_at": "2026-10-01T08:10:00+05:00",
    "ended_at": "2026-10-01T08:32:00+05:00",
    "fare": 2400,
    "payment_method": "card",
    "commission_amount": 360,
}
DAY = {"work_date": "2026-10-01"}


@pytest.fixture
def app(db):
    return create_app(db.database)


def logged_in(app, db, email, password="horse-battery-9"):
    driver_id = create_driver(db, email, password, name=email)
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200
    c.shift_id = day_shift(db, driver_id)  # this driver's shift on 2026-10-01
    return c


def trip(client, **changes):
    return {**TRIP, "shift_id": client.shift_id, **changes}


@pytest.fixture
def alice(app, db):
    return logged_in(app, db, "alice@example.com")


@pytest.fixture
def bob(app, db):
    return logged_in(app, db, "bob@example.com")


# --- isolation between drivers ---


def test_driver_does_not_see_other_drivers_trips(alice, bob):
    assert alice.post("/api/v1/trips", json=trip(alice)).status_code == 201
    assert bob.get("/api/v1/trips", params=DAY).json() == []
    # Bob sees only his own (empty) shift on that day, none of Alice's trips
    assert bob.get("/api/v1/days").json() == [{"work_date": "2026-10-01", "trips_count": 0, "net_income": 0}]
    bob_summary = bob.get("/api/v1/summary", params=DAY).json()
    assert bob_summary["trips_count"] == 0 and bob_summary["revenue"] == 0
    assert len(alice.get("/api/v1/trips", params=DAY).json()) == 1


def test_same_trip_id_for_two_drivers_via_api(alice, bob):
    assert alice.post("/api/v1/trips", json=trip(alice)).status_code == 201
    # Not a duplicate and not a conflict: Bob's own trip with the same id
    assert bob.post("/api/v1/trips", json=trip(bob, fare=9999)).status_code == 201
    assert alice.get("/api/v1/trips", params=DAY).json()[0]["fare"] == 2400
    assert bob.get("/api/v1/trips", params=DAY).json()[0]["fare"] == 9999


@pytest.mark.parametrize(
    "method, path, kwargs",
    [
        ("GET", "/api/v1/days", {}),
        ("GET", "/api/v1/trips", {"params": DAY}),
        ("GET", "/api/v1/summary", {"params": DAY}),
        ("POST", "/api/v1/trips", {"json": TRIP}),
    ],
)
def test_trip_endpoints_require_auth(app, db, method, path, kwargs):
    r = TestClient(app).request(method, path, **kwargs)
    assert r.status_code == 401
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"] == 0


def test_drivers_cannot_delete_their_own_account(alice):
    r = alice.request("DELETE", "/api/v1/me", json={"password": "horse-battery-9"})
    assert r.status_code == 405
    assert alice.get("/api/v1/me").status_code == 200
