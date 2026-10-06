import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TRIP = {"id": "t1", "start": "2026-10-01T08:10:00+05:00", "end": "2026-10-01T08:32:00+05:00",
        "amount": 2400, "payment": "card", "commission": 360}
DAY = {"date": "2026-10-01"}


@pytest.fixture
def app(db):
    return create_app(db)


def signed_up(app, email, password="password123"):
    c = TestClient(app)
    assert c.post("/api/auth/register",
                  json={"email": email, "password": password, "name": email}).status_code == 201
    return c


@pytest.fixture
def alice(app):
    return signed_up(app, "alice@example.com")


@pytest.fixture
def bob(app):
    return signed_up(app, "bob@example.com")


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


# --- account deletion ---

def delete_account(client, password="password123"):
    return client.request("DELETE", "/api/me", json={"password": password})


def test_delete_account_removes_driver_trips_and_sessions(app, db, alice, bob):
    alice.post("/api/trips", json=TRIP)
    bob.post("/api/trips", json=TRIP)
    second_device = TestClient(app)
    second_device.post("/api/auth/login", json={"email": "alice@example.com", "password": "password123"})

    assert delete_account(alice).status_code == 204

    assert alice.get("/api/me").status_code == 401
    assert second_device.get("/api/me").status_code == 401  # every session is gone
    with db.connection() as conn:
        owners = conn.execute(
            "SELECT d.email FROM trips t JOIN drivers d ON d.id = t.driver_id"
        ).fetchall()
        assert [r["email"] for r in owners] == ["bob@example.com"]  # Bob is untouched
    assert len(bob.get("/api/trips", params=DAY).json()) == 1


def test_deleted_email_can_register_again(app, alice):
    delete_account(alice)
    again = signed_up(app, "alice@example.com")
    assert again.get("/api/days").json() == []  # fresh account, no old data


def test_delete_account_requires_correct_password(alice):
    r = delete_account(alice, password="wrong-password")
    assert r.status_code == 403
    assert alice.get("/api/me").status_code == 200


def test_delete_account_password_is_rate_limited(alice):
    for _ in range(5):
        assert delete_account(alice, password="wrong-password").status_code == 403
    assert delete_account(alice).status_code == 429
    assert alice.get("/api/me").status_code == 200


def test_delete_account_requires_auth(app):
    assert delete_account(TestClient(app)).status_code == 401
