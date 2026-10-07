import pytest
from fastapi.testclient import TestClient

from tests.factories import create_driver
from app.main import create_app

TRIP = {"id": "t1", "start": "2026-10-01T08:10:00+05:00", "end": "2026-10-01T08:32:00+05:00",
        "amount": 2400, "payment": "card", "commission": 360}
DAY = {"date": "2026-10-01"}


@pytest.fixture
def app(db):
    return create_app(db)


def logged_in(app, db, email, password="password123"):
    create_driver(db, email, password, name=email)
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200
    return c


@pytest.fixture
def alice(app, db):
    return logged_in(app, db, "alice@example.com")


@pytest.fixture
def bob(app, db):
    return logged_in(app, db, "bob@example.com")


# --- isolation between drivers ---

def test_driver_does_not_see_other_drivers_trips(alice, bob):
    assert alice.post("/api/trips", json=TRIP).status_code == 201
    assert bob.get("/api/trips", params=DAY).json() == []
    assert bob.get("/api/days").json() == []
    bob_summary = bob.get("/api/summary", params=DAY).json()
    assert bob_summary["count"] == 0 and bob_summary["revenue"] == 0
    assert len(alice.get("/api/trips", params=DAY).json()) == 1


def test_same_trip_id_for_two_drivers_via_api(alice, bob):
    assert alice.post("/api/trips", json=TRIP).status_code == 201
    # Not a duplicate and not a conflict: Bob's own trip with the same id
    assert bob.post("/api/trips", json={**TRIP, "amount": 9999}).status_code == 201
    assert alice.get("/api/trips", params=DAY).json()[0]["amount"] == 2400
    assert bob.get("/api/trips", params=DAY).json()[0]["amount"] == 9999


@pytest.mark.parametrize("method, path, kwargs", [
    ("GET", "/api/days", {}),
    ("GET", "/api/trips", {"params": DAY}),
    ("GET", "/api/summary", {"params": DAY}),
    ("POST", "/api/trips", {"json": TRIP}),
])
def test_trip_endpoints_require_auth(app, db, method, path, kwargs):
    r = TestClient(app).request(method, path, **kwargs)
    assert r.status_code == 401
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"] == 0


def test_drivers_cannot_delete_their_own_account(alice):
    r = alice.request("DELETE", "/api/me", json={"password": "password123"})
    assert r.status_code == 405
    assert alice.get("/api/me").status_code == 200
