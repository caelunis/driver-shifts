from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import shifts as shifts_service
from tests.api import code, error
from tests.conftest import NOW
from tests.factories import create_driver, day_shift

TRIP = {
    "start": "2026-10-01T08:10:00+05:00",
    "end": "2026-10-01T08:32:00+05:00",
    "amount": 2400,
    "payment": "card",
    "commission": 360,
}


@pytest.fixture
def app(db):
    return create_app(db)


def logged_in(app, email, password="horse-battery-9"):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200
    return c


@pytest.fixture
def driver(app, driver_id):
    return logged_in(app, "driver@example.com")


def at(day_time: str) -> str:
    return f"2026-10-{day_time}:00+05:00"  # at("01T08:00") -> 2026-10-01T08:00:00+05:00


# --- starting a shift ---


def test_start_now(driver):
    r = driver.post("/api/shifts", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open" and body["end"] is None
    assert datetime.fromisoformat(body["start"]) == NOW
    assert body["start"].endswith("+05:00")  # in the driver's timezone
    assert body["local_day"] == "2026-10-03"
    assert driver.get("/api/shifts/current").json()["id"] == body["id"]


def test_no_current_shift_is_null(driver):
    r = driver.get("/api/shifts/current")
    assert r.status_code == 200 and r.json() is None


def test_only_one_open_shift(driver):
    driver.post("/api/shifts", json={})
    r = driver.post("/api/shifts", json={"start": at("03T11:00")})
    assert r.status_code == 409
    assert code(r) == "shift_already_open"


def test_concurrent_starts_open_exactly_one_shift(db, driver_id):
    def attempt(_):
        try:
            shifts_service.start(db, driver_id)
            return "ok"
        except Exception as e:
            return type(e).__name__

    # Several rounds: without the driver lock about one round in ten deadlocked
    for _ in range(10):
        with db.connection() as conn:
            conn.execute("DELETE FROM shifts")
        with ThreadPoolExecutor(max_workers=6) as ex:
            results = list(ex.map(attempt, range(6)))
        assert results.count("ok") == 1
        # Never a database error such as DeadlockDetected
        assert set(results) == {"ok", "ConflictError"}, results


def test_enter_past_shift(driver):
    r = driver.post("/api/shifts", json={"start": at("02T08:00"), "end": at("02T18:00"), "note": "дневная"})
    assert r.status_code == 201
    body = r.json()
    assert (body["status"], body["note"], body["summary"]["duration_min"]) == ("closed", "дневная", 600)


def test_shifts_cannot_overlap(driver):
    driver.post("/api/shifts", json={"start": at("02T08:00"), "end": at("02T18:00")})
    r = driver.post("/api/shifts", json={"start": at("02T17:00"), "end": at("02T20:00")})
    assert r.status_code == 409
    assert code(r) == "shift_overlap"
    # Touching ends are fine: [08:00, 18:00) and [18:00, 20:00)
    assert (
        driver.post("/api/shifts", json={"start": at("02T18:00"), "end": at("02T20:00")}).status_code == 201
    )


@pytest.mark.parametrize(
    "body, field, type_",
    [
        ({"start": at("03T12:30")}, "start", "in_future"),  # now is 10-03 12:00
        ({"start": at("03T10:00"), "end": at("03T13:00")}, "end", "in_future"),
        ({"start": "2026-09-25T08:00:00+05:00"}, "start", "too_old"),  # more than 7 days back
        ({"start": at("01T08:00"), "end": at("02T08:01")}, "end", "shift_too_long"),
        ({"start": at("01T08:00"), "end": at("01T07:00")}, "end", "end_before_start"),
        ({"end": at("01T08:00")}, "end", "start_required"),
        ({"start": "2026-10-01T08:00:00"}, "start", "timezone_required"),
        ({"note": "x" * 501}, "note", "string_too_long"),
    ],
)
def test_start_validation(driver, body, field, type_):
    r = driver.post("/api/shifts", json=body)
    assert r.status_code == 422
    assert error(r) == (field, type_)


def test_clock_skew_tolerance(driver):
    # A client clock a few minutes ahead is accepted
    assert driver.post("/api/shifts", json={"start": at("03T12:04")}).status_code == 201


def test_exactly_24_hours_is_allowed(driver):
    r = driver.post("/api/shifts", json={"start": at("01T08:00"), "end": at("02T08:00")})
    assert r.status_code == 201


# --- closing ---


def test_close_now_and_not_twice(driver):
    shift = driver.post("/api/shifts", json={"start": at("03T08:00")}).json()
    r = driver.post(f"/api/shifts/{shift['id']}/close", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
    assert datetime.fromisoformat(r.json()["end"]) == NOW
    assert driver.get("/api/shifts/current").json() is None
    again = driver.post(f"/api/shifts/{shift['id']}/close", json={})
    assert again.status_code == 409 and code(again) == "shift_already_closed"


def test_cannot_close_before_last_trip(driver):
    shift = driver.post("/api/shifts", json={"start": at("03T08:00")}).json()
    driver.post(
        "/api/trips", json={**TRIP, "shift_id": shift["id"], "start": at("03T09:00"), "end": at("03T09:40")}
    )
    r = driver.post(f"/api/shifts/{shift['id']}/close", json={"end": at("03T09:30")})
    assert r.status_code == 422
    assert error(r) == ("end", "before_last_trip")
    assert driver.post(f"/api/shifts/{shift['id']}/close", json={"end": at("03T09:40")}).status_code == 200


def test_forgotten_shift_can_always_be_closed(db, driver, driver_id):
    """Opened 10 days ago and never closed: older than the 7-day window, still closable."""
    started = NOW - timedelta(days=10)
    shift = shifts_service.start(db, driver_id, started, by_admin=True)
    assert driver.get("/api/shifts/current").json()["id"] == shift.id

    too_long = driver.post(f"/api/shifts/{shift.id}/close", json={})  # now = 10 days later
    assert too_long.status_code == 422 and error(too_long) == ("end", "shift_too_long")

    end = (started + timedelta(hours=9)).isoformat()
    r = driver.post(f"/api/shifts/{shift.id}/close", json={"end": end})
    assert r.status_code == 200 and r.json()["summary"]["duration_min"] == 540
    # ...and the driver can start working again
    assert driver.post("/api/shifts", json={}).status_code == 201


def test_close_another_drivers_shift_is_404(db, driver):
    other = create_driver(db, "other@example.com", "horse-battery-9")
    shift = shifts_service.start(db, other)
    assert driver.post(f"/api/shifts/{shift.id}/close", json={}).status_code == 404
    assert driver.get(f"/api/shifts/{shift.id}").status_code == 404


# --- trips belong to a shift ---


def test_trip_requires_a_shift(driver):
    r = driver.post("/api/trips", json=TRIP)
    assert r.status_code == 422 and error(r) == ("shift_id", "missing")


def test_trip_in_unknown_or_foreign_shift(db, driver):
    other = create_driver(db, "other@example.com", "horse-battery-9")
    foreign = day_shift(db, other)
    for shift_id in (foreign, 999):
        r = driver.post("/api/trips", json={**TRIP, "shift_id": shift_id})
        assert r.status_code == 422 and error(r) == ("shift_id", "shift_not_found")


@pytest.mark.parametrize(
    "start, end, field, type_",
    [
        (at("01T07:50"), at("01T08:20"), "start", "outside_shift"),  # shift is 08:00-18:00
        (at("01T17:50"), at("01T18:10"), "end", "outside_shift"),
    ],
)
def test_trip_must_fit_its_shift(db, driver, driver_id, start, end, field, type_):
    shift = day_shift(db, driver_id, "2026-10-01", start="08:00", end="18:00")
    r = driver.post("/api/trips", json={**TRIP, "shift_id": shift, "start": start, "end": end})
    assert r.status_code == 422 and error(r) == (field, type_)


def test_trip_in_open_shift_cannot_end_in_future(driver):
    shift = driver.post("/api/shifts", json={"start": at("03T08:00")}).json()
    r = driver.post(
        "/api/trips", json={**TRIP, "shift_id": shift["id"], "start": at("03T11:50"), "end": at("03T12:30")}
    )
    assert r.status_code == 422 and error(r) == ("end", "in_future")


def test_shift_older_than_window_is_locked_for_the_driver(db, driver, driver_id):
    old = shifts_service.start(
        db,
        driver_id,
        datetime.fromisoformat("2026-09-20T08:00:00+05:00"),
        datetime.fromisoformat("2026-09-20T18:00:00+05:00"),
        by_admin=True,
    )
    r = driver.post(
        "/api/trips",
        json={
            **TRIP,
            "shift_id": old.id,
            "start": "2026-09-20T09:00:00+05:00",
            "end": "2026-09-20T09:30:00+05:00",
        },
    )
    assert r.status_code == 422 and error(r) == ("shift_id", "too_old")


# --- days and summaries come from shifts ---


def test_night_shift_keeps_its_trips_on_the_start_day(db, driver, driver_id):
    shift = day_shift(db, driver_id, "2026-10-01", start="20:00", end="23:59")
    with db.connection() as conn:  # extend to 04:00 next day (day_shift stays within a date)
        conn.execute("UPDATE shifts SET ended_at = '2026-10-02 04:00+05' WHERE id = %s", (shift,))
    driver.post(
        "/api/trips", json={**TRIP, "shift_id": shift, "start": at("02T01:00"), "end": at("02T01:30")}
    )
    assert [t["start"] for t in driver.get("/api/trips", params={"date": "2026-10-01"}).json()] == [
        "2026-10-02T01:00:00+05:00"
    ]
    assert driver.get("/api/trips", params={"date": "2026-10-02"}).json() == []
    assert driver.get("/api/days").json() == [{"date": "2026-10-01", "count": 1, "net": 2040}]


def test_day_of_a_shift_is_local_not_utc(driver):
    # 02:00 +05:00 is 21:00 UTC of the previous day
    body = driver.post("/api/shifts", json={"start": at("02T02:00"), "end": at("02T06:00")}).json()
    assert body["local_day"] == "2026-10-02"


def test_shift_list_detail_and_summaries(db, driver, driver_id):
    morning = day_shift(db, driver_id, "2026-10-01", start="08:00", end="12:00")
    evening = day_shift(db, driver_id, "2026-10-01", start="18:00", end="20:00")
    driver.post("/api/trips", json={**TRIP, "shift_id": morning})
    driver.post(
        "/api/trips",
        json={
            **TRIP,
            "id": "e1",
            "shift_id": evening,
            "start": at("01T18:30"),
            "end": at("01T19:00"),
            "amount": 1000,
            "commission": 100,
            "payment": "cash",
        },
    )
    listed = driver.get("/api/shifts", params={"date": "2026-10-01"}).json()
    assert [s["id"] for s in listed] == [morning, evening]
    m = listed[0]["summary"]
    assert (m["count"], m["revenue"], m["net"], m["duration_min"], m["net_per_hour"]) == (
        1,
        2400,
        2040,
        240,
        510,
    )

    detail = driver.get(f"/api/shifts/{evening}").json()
    assert [t["id"] for t in detail["trips"]] == ["e1"]
    assert detail["summary"]["cash"] == {"count": 1, "amount": 1000}

    day = driver.get("/api/summary", params={"date": "2026-10-01"}).json()
    assert (day["shifts"], day["count"], day["revenue"], day["net"]) == (2, 2, 3400, 2940)


def test_open_shift_summary_runs_up_to_now(driver):
    shift = driver.post("/api/shifts", json={"start": at("03T10:00")}).json()
    assert shift["summary"]["duration_min"] == 120  # now is 12:00


# --- roles ---


def test_admins_have_no_shifts_of_their_own(app, db):
    create_driver(db, "admin@example.com", "horse-battery-9", role="admin")
    admin = logged_in(app, "admin@example.com")
    assert admin.get("/api/shifts/current").status_code == 403
    assert admin.post("/api/shifts", json={}).status_code == 403


def test_admin_reads_driver_shifts(app, db, driver, driver_id):
    shift = day_shift(db, driver_id)
    driver.post("/api/trips", json={**TRIP, "shift_id": shift})
    create_driver(db, "admin@example.com", "horse-battery-9", role="admin")
    admin = logged_in(app, "admin@example.com")
    base = f"/api/admin/drivers/{driver_id}/shifts"
    assert [s["id"] for s in admin.get(base, params={"date": "2026-10-01"}).json()] == [shift]
    assert len(admin.get(f"{base}/{shift}").json()["trips"]) == 1
    assert driver.get(base, params={"date": "2026-10-01"}).status_code == 403
