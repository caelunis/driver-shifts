"""Stricter trip rules and the single error format."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api import code, error
from tests.factories import day_shift

TRIP = {"id": "t1", "shift_id": 1, "start": "2026-10-01T08:10:00+05:00",
        "end": "2026-10-01T08:32:00+05:00", "amount": 2400, "payment": "card", "commission": 360}


@pytest.fixture
def app(db):
    return create_app(db)


@pytest.fixture
def driver(app, db, driver_id):
    day_shift(db, driver_id)
    c = TestClient(app)
    c.post("/api/auth/login", json={"email": "driver@example.com", "password": "horse-battery-9"})
    return c


def at(time: str) -> str:
    return f"2026-10-01T{time}:00+05:00"


# --- trips ---

@pytest.mark.parametrize("start, end, expected", [
    ("08:10:00", "08:10:30", "trip_too_short"),
    ("08:00:00", "14:00:01", "trip_too_long"),
])
def test_trip_duration_bounds(driver, start, end, expected):
    r = driver.post("/api/trips", json={**TRIP, "start": f"2026-10-01T{start}+05:00",
                                        "end": f"2026-10-01T{end}+05:00"})
    assert r.status_code == 422 and error(r) == ("end", expected)


def test_trip_of_exactly_six_hours_is_fine(driver):
    r = driver.post("/api/trips", json={**TRIP, "start": at("08:00"), "end": at("14:00")})
    assert r.status_code == 201


def test_amount_cap(driver):
    r = driver.post("/api/trips", json={**TRIP, "amount": 500_001})
    assert r.status_code == 422 and error(r) == ("amount", "less_than_equal")
    assert driver.post("/api/trips", json={**TRIP, "amount": 500_000}).status_code == 201


def test_trips_cannot_overlap(driver):
    driver.post("/api/trips", json=TRIP)  # 08:10-08:32
    r = driver.post("/api/trips", json={**TRIP, "id": "t2", "start": at("08:30"), "end": at("08:50")})
    assert r.status_code == 409 and code(r) == "trip_overlap"
    assert r.json()["error"]["ctx"] == {"trip_id": "t1"}
    # Back to back is fine: ranges are half-open
    r = driver.post("/api/trips", json={**TRIP, "id": "t2", "start": at("08:32"), "end": at("08:50")})
    assert r.status_code == 201


def test_edit_cannot_create_overlap(driver):
    driver.post("/api/trips", json=TRIP)
    driver.post("/api/trips", json={**TRIP, "id": "t2", "start": at("09:00"), "end": at("09:20")})
    r = driver.patch("/api/trips/t2", json={"start": at("08:20")})
    assert r.status_code == 409 and code(r) == "trip_overlap"
    # A trip does not overlap with its own old position
    assert driver.patch("/api/trips/t1", json={"end": at("08:40")}).status_code == 200


def test_resending_a_trip_is_still_idempotent(driver):
    assert driver.post("/api/trips", json=TRIP).status_code == 201
    assert driver.post("/api/trips", json=TRIP).status_code == 200


def test_database_rejects_overlap_too(db, driver):
    driver.post("/api/trips", json=TRIP)
    import psycopg
    with pytest.raises(psycopg.errors.ExclusionViolation), db.connection() as conn:
        conn.execute("INSERT INTO trips (driver_id, id, shift_id, start_at, end_at,"
                     " start_offset_min, end_offset_min, amount, payment, commission)"
                     " SELECT driver_id, 'x', shift_id, start_at, end_at, 300, 300, 100, 'cash', 0"
                     " FROM trips WHERE id = 't1'")


def test_unknown_trip_field_is_rejected(driver):
    r = driver.post("/api/trips", json={**TRIP, "ammount": 100})
    assert r.status_code == 422 and error(r) == ("ammount", "extra_forbidden")


# --- error format ---

def test_validation_error_shape(driver):
    r = driver.post("/api/trips", json={**TRIP, "amount": 0})
    assert r.json() == {"error": {
        "code": "validation_error", "message": "Some fields are invalid", "ctx": {},
        "fields": [{"field": "amount", "code": "greater_than",
                    "message": "Input should be greater than 0", "ctx": {"gt": 0}}],
    }}


def test_conflict_error_shape(driver):
    driver.post("/api/shifts", json={"start": "2026-10-03T10:00:00+05:00"})
    r = driver.post("/api/shifts", json={})
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "shift_already_open", "message": "Close the open shift first",
                                 "fields": [], "ctx": {}}


@pytest.mark.parametrize("method, path, status, expected", [
    ("GET", "/api/me", 401, "not_authenticated"),
    ("GET", "/api/nope", 404, "not_found"),
    ("PUT", "/api/health", 405, "method_not_allowed"),
])
def test_framework_errors_use_the_same_format(app, method, path, status, expected):
    r = TestClient(app).request(method, path)
    assert r.status_code == status and code(r) == expected
    assert set(r.json()["error"]) == {"code", "message", "fields", "ctx"}


def test_rejected_input_is_not_echoed(app, db):
    # A password must never come back in an error response
    r = TestClient(app).post("/api/auth/login", json={"email": "x@example.com",
                                                      "password": "x" * 200})
    assert r.status_code == 422 and "xxxx" not in r.text


def test_too_many_logins_tells_when_to_retry(app, driver_id):
    c = TestClient(app)
    for _ in range(5):
        c.post("/api/auth/login", json={"email": "driver@example.com", "password": "wrong-pass"})
    r = c.post("/api/auth/login", json={"email": "driver@example.com", "password": "wrong-pass"})
    assert r.status_code == 429 and code(r) == "too_many_attempts"
    assert int(r.headers["Retry-After"]) == r.json()["error"]["ctx"]["retry_after"] > 0
