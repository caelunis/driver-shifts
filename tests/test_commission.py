import pytest
from fastapi.testclient import TestClient

from app.accounts import admin_update_driver, create_driver
from app.commission import commission_for
from app.main import create_app

TRIP = {"start": "2026-10-01T08:10:00+05:00", "end": "2026-10-01T08:32:00+05:00",
        "amount": 2350, "payment": "card"}


@pytest.mark.parametrize("amount, pct, expected", [
    (2400, 15, 360),
    (2350, 15, 353),      # 352.5 rounds half up (Python's round() would give 352)
    (1000, 12.35, 124),   # 123.5: exact decimal math, no float drift to 123.4999…
    (1000, 0, 0),
    (999, 33.33, 333),
])
def test_commission_for(amount, pct, expected):
    assert commission_for(amount, pct) == expected


@pytest.fixture
def driver_id(db):
    return create_driver(db, "driver@example.com", "driver-pass")


@pytest.fixture
def driver(db, driver_id):
    c = TestClient(create_app(db))
    c.post("/api/auth/login", json={"email": "driver@example.com", "password": "driver-pass"})
    return c


def set_pct(db, driver_id, pct):
    admin_update_driver(db, driver_id, {"default_commission_pct": pct})


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
    [err] = r.json()["detail"]
    assert err["type"] == "commission_fixed"
    assert err["loc"] == ["body", "commission"]
    assert err["ctx"]["expected"] == 353


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
    assert r.json()["detail"][0]["type"] == "commission_exceeds_amount"


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
    assert r.json()["detail"][0]["loc"] == ["body", "commission"]
    assert r.json()["detail"][0]["type"] == "missing"
