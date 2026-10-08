import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api import error, field_ctx
from tests.factories import create_driver, day_shift, set_commission_pct

# shift_id 1: the day shift created by the `driver` fixture
TRIP = {
    "shift_id": 1,
    "start": "2026-10-01T08:10:00+05:00",
    "end": "2026-10-01T08:32:00+05:00",
    "amount": 2350,
    "payment": "card",
}


@pytest.fixture
def driver_id(db):
    return create_driver(db, "driver@example.com", "driver-pass")


@pytest.fixture
def driver(db, driver_id):
    assert day_shift(db, driver_id) == 1
    c = TestClient(create_app(db))
    c.post("/api/auth/login", json={"email": "driver@example.com", "password": "driver-pass"})
    return c


def set_pct(db, driver_id, pct):
    set_commission_pct(db, driver_id, pct)


# --- percent set by the admin: the server computes the commission ---


def test_commission_is_computed_when_omitted(db, driver, driver_id):
    set_pct(db, driver_id, 15)
    r = driver.post("/api/trips", json=TRIP)
    assert r.status_code == 201
    assert r.json()["commission"] == 353


def test_matching_commission_is_accepted(db, driver, driver_id):
    set_pct(db, driver_id, 15)
    assert driver.post("/api/trips", json={**TRIP, "commission": 353}).status_code == 201


def test_different_commission_is_rejected(db, driver, driver_id):
    set_pct(db, driver_id, 15)
    r = driver.post("/api/trips", json={**TRIP, "commission": 100})
    assert r.status_code == 422
    assert error(r) == ("commission", "commission_fixed")
    assert field_ctx(r)["expected"] == 353


def test_repeat_without_commission_is_not_a_duplicate(db, driver, driver_id):
    set_pct(db, driver_id, 15)
    first = driver.post("/api/trips", json=TRIP)
    again = driver.post("/api/trips", json=TRIP)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]


def test_rounded_commission_reaching_amount_is_rejected(db, driver, driver_id):
    set_pct(db, driver_id, 50)
    r = driver.post("/api/trips", json={**TRIP, "amount": 1})  # 0.5 rounds up to 1 == amount
    assert r.status_code == 422
    assert error(r) == ("commission", "commission_exceeds_amount")


def test_percent_change_does_not_touch_old_trips(db, driver, driver_id):
    set_pct(db, driver_id, 15)
    driver.post("/api/trips", json=TRIP)
    set_pct(db, driver_id, 20)
    [trip] = driver.get("/api/trips", params={"date": "2026-10-01"}).json()
    assert trip["commission"] == 353


# --- no percent: the driver enters the commission ---


def test_manual_commission_without_percent(driver):
    r = driver.post("/api/trips", json={**TRIP, "commission": 100})
    assert r.status_code == 201
    assert r.json()["commission"] == 100


def test_commission_required_without_percent(driver):
    r = driver.post("/api/trips", json=TRIP)
    assert r.status_code == 422
    assert error(r) == ("commission", "missing")
