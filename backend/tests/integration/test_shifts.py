from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.shifts import ShiftService
from tests.api import code, error, tid
from tests.conftest import NOW
from tests.factories import create_driver, day_shift

TRIP = {
    "started_at": "2026-10-01T08:10:00+05:00",
    "ended_at": "2026-10-01T08:32:00+05:00",
    "fare": 2400,
    "payment_method": "card",
    "commission_amount": 360,
}


@pytest.fixture
def app(db):
    return create_app(db.database)


def logged_in(app, email, password="horse-battery-9"):
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200
    return c


@pytest.fixture
def driver(app, driver_id):
    return logged_in(app, "driver@example.com")


def at(day_time: str) -> str:
    return f"2026-10-{day_time}:00+05:00"  # at("01T08:00") -> 2026-10-01T08:00:00+05:00


# --- starting a shift ---


def test_start_now(driver):
    r = driver.post("/api/v1/shifts", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open" and body["ended_at"] is None
    assert datetime.fromisoformat(body["started_at"]) == NOW
    assert body["started_at"].endswith("+05:00")  # in the driver's timezone
    assert body["work_date"] == "2026-10-03"
    assert driver.get("/api/v1/shifts/current").json()["id"] == body["id"]


def test_no_current_shift_is_null(driver):
    r = driver.get("/api/v1/shifts/current")
    assert r.status_code == 200 and r.json() is None


def test_only_one_open_shift(driver):
    driver.post("/api/v1/shifts", json={})
    r = driver.post("/api/v1/shifts", json={"started_at": at("03T11:00")})
    assert r.status_code == 409
    assert code(r) == "shift_already_open"


def test_concurrent_starts_open_exactly_one_shift(db, driver_id):
    def attempt(_):
        try:
            db.service(ShiftService).start(driver_id)
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
    r = driver.post(
        "/api/v1/shifts", json={"started_at": at("02T08:00"), "ended_at": at("02T18:00"), "note": "дневная"}
    )
    assert r.status_code == 201
    body = r.json()
    assert (body["status"], body["note"], body["summary"]["duration_minutes"]) == ("closed", "дневная", 600)


def test_shifts_cannot_overlap(driver):
    driver.post("/api/v1/shifts", json={"started_at": at("02T08:00"), "ended_at": at("02T18:00")})
    r = driver.post("/api/v1/shifts", json={"started_at": at("02T17:00"), "ended_at": at("02T20:00")})
    assert r.status_code == 409
    assert code(r) == "shift_overlap"
    # Touching ends are fine: [08:00, 18:00) and [18:00, 20:00)
    assert (
        driver.post(
            "/api/v1/shifts", json={"started_at": at("02T18:00"), "ended_at": at("02T20:00")}
        ).status_code
        == 201
    )


@pytest.mark.parametrize(
    "body, field, type_",
    [
        ({"started_at": at("03T12:30")}, "started_at", "in_future"),  # now is 10-03 12:00
        ({"started_at": at("03T10:00"), "ended_at": at("03T13:00")}, "ended_at", "in_future"),
        ({"started_at": "2026-09-25T08:00:00+05:00"}, "started_at", "too_old"),  # more than 7 days back
        ({"started_at": at("01T08:00"), "ended_at": at("02T08:01")}, "ended_at", "shift_too_long"),
        ({"started_at": at("01T08:00"), "ended_at": at("01T07:00")}, "ended_at", "end_before_start"),
        ({"ended_at": at("01T08:00")}, "ended_at", "start_required"),
        ({"started_at": "2026-10-01T08:00:00"}, "started_at", "timezone_required"),
        ({"note": "x" * 501}, "note", "string_too_long"),
    ],
)
def test_start_validation(driver, body, field, type_):
    r = driver.post("/api/v1/shifts", json=body)
    assert r.status_code == 422
    assert error(r) == (field, type_)


def test_clock_skew_tolerance(driver):
    # A client clock a few minutes ahead is accepted
    assert driver.post("/api/v1/shifts", json={"started_at": at("03T12:04")}).status_code == 201


def test_exactly_24_hours_is_allowed(driver):
    r = driver.post("/api/v1/shifts", json={"started_at": at("01T08:00"), "ended_at": at("02T08:00")})
    assert r.status_code == 201


# --- closing ---


def test_close_now_and_not_twice(driver):
    shift = driver.post("/api/v1/shifts", json={"started_at": at("03T08:00")}).json()
    r = driver.post(f"/api/v1/shifts/{shift['id']}/close", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
    assert datetime.fromisoformat(r.json()["ended_at"]) == NOW
    assert driver.get("/api/v1/shifts/current").json() is None
    again = driver.post(f"/api/v1/shifts/{shift['id']}/close", json={})
    assert again.status_code == 409 and code(again) == "shift_already_closed"


def test_cannot_close_before_last_trip(driver):
    shift = driver.post("/api/v1/shifts", json={"started_at": at("03T08:00")}).json()
    driver.post(
        "/api/v1/trips",
        json={**TRIP, "shift_id": shift["id"], "started_at": at("03T09:00"), "ended_at": at("03T09:40")},
    )
    r = driver.post(f"/api/v1/shifts/{shift['id']}/close", json={"ended_at": at("03T09:30")})
    assert r.status_code == 422
    assert error(r) == ("ended_at", "before_last_trip")
    assert (
        driver.post(f"/api/v1/shifts/{shift['id']}/close", json={"ended_at": at("03T09:40")}).status_code
        == 200
    )


def test_forgotten_shift_can_always_be_closed(db, driver, driver_id):
    """Opened 10 days ago and never closed: older than the 7-day window, still closable."""
    started = NOW - timedelta(days=10)
    shift = db.service(ShiftService).start(driver_id, started, by_admin=True)
    assert driver.get("/api/v1/shifts/current").json()["id"] == str(shift.id)

    too_long = driver.post(f"/api/v1/shifts/{shift.id}/close", json={})  # now = 10 days later
    assert too_long.status_code == 422 and error(too_long) == ("ended_at", "shift_too_long")

    end = (started + timedelta(hours=9)).isoformat()
    r = driver.post(f"/api/v1/shifts/{shift.id}/close", json={"ended_at": end})
    assert r.status_code == 200 and r.json()["summary"]["duration_minutes"] == 540
    # ...and the driver can start working again
    assert driver.post("/api/v1/shifts", json={}).status_code == 201


def test_close_another_drivers_shift_is_404(db, driver):
    other = create_driver(db, "other@example.com", "horse-battery-9")
    shift = db.service(ShiftService).start(other)
    assert driver.post(f"/api/v1/shifts/{shift.id}/close", json={}).status_code == 404
    assert driver.get(f"/api/v1/shifts/{shift.id}").status_code == 404


# --- trips belong to a shift ---


def test_trip_requires_a_shift(driver):
    r = driver.post("/api/v1/trips", json=TRIP)
    assert r.status_code == 422 and error(r) == ("shift_id", "missing")


def test_trip_in_unknown_or_foreign_shift(db, driver):
    other = create_driver(db, "other@example.com", "horse-battery-9")
    foreign = day_shift(db, other)
    for shift_id in (foreign, "00000000-0000-4000-8000-000000000999"):
        r = driver.post("/api/v1/trips", json={**TRIP, "shift_id": shift_id})
        assert r.status_code == 422 and error(r) == ("shift_id", "shift_not_found")


@pytest.mark.parametrize(
    "start, end, field, type_",
    [
        (at("01T07:50"), at("01T08:20"), "started_at", "outside_shift"),  # shift is 08:00-18:00
        (at("01T17:50"), at("01T18:10"), "ended_at", "outside_shift"),
    ],
)
def test_trip_must_fit_its_shift(db, driver, driver_id, start, end, field, type_):
    shift = day_shift(db, driver_id, "2026-10-01", start="08:00", end="18:00")
    r = driver.post("/api/v1/trips", json={**TRIP, "shift_id": shift, "started_at": start, "ended_at": end})
    assert r.status_code == 422 and error(r) == (field, type_)


def test_trip_in_open_shift_cannot_end_in_future(driver):
    shift = driver.post("/api/v1/shifts", json={"started_at": at("03T08:00")}).json()
    r = driver.post(
        "/api/v1/trips",
        json={**TRIP, "shift_id": shift["id"], "started_at": at("03T11:50"), "ended_at": at("03T12:30")},
    )
    assert r.status_code == 422 and error(r) == ("ended_at", "in_future")


def test_shift_older_than_window_is_locked_for_the_driver(db, driver, driver_id):
    old = db.service(ShiftService).start(
        driver_id,
        datetime.fromisoformat("2026-09-20T08:00:00+05:00"),
        datetime.fromisoformat("2026-09-20T18:00:00+05:00"),
        by_admin=True,
    )
    r = driver.post(
        "/api/v1/trips",
        json={
            **TRIP,
            "shift_id": str(old.id),
            "started_at": "2026-09-20T09:00:00+05:00",
            "ended_at": "2026-09-20T09:30:00+05:00",
        },
    )
    assert r.status_code == 422 and error(r) == ("shift_id", "too_old")


# --- days and summaries come from shifts ---


def test_night_shift_keeps_its_trips_on_the_start_day(db, driver, driver_id):
    shift = day_shift(db, driver_id, "2026-10-01", start="20:00", end="23:59")
    with db.connection() as conn:  # extend to 04:00 next day (day_shift stays within a date)
        conn.execute("UPDATE shifts SET ended_at = '2026-10-02 04:00+05' WHERE id = %s", (shift,))
    driver.post(
        "/api/v1/trips",
        json={**TRIP, "shift_id": shift, "started_at": at("02T01:00"), "ended_at": at("02T01:30")},
    )
    assert [
        t["started_at"] for t in driver.get("/api/v1/trips", params={"work_date": "2026-10-01"}).json()
    ] == ["2026-10-02T01:00:00+05:00"]
    assert driver.get("/api/v1/trips", params={"work_date": "2026-10-02"}).json() == []
    assert driver.get("/api/v1/days").json() == [
        {"work_date": "2026-10-01", "trips_count": 1, "net_income": 2040}
    ]


def test_day_of_a_shift_is_local_not_utc(driver):
    # 02:00 +05:00 is 21:00 UTC of the previous day
    body = driver.post(
        "/api/v1/shifts", json={"started_at": at("02T02:00"), "ended_at": at("02T06:00")}
    ).json()
    assert body["work_date"] == "2026-10-02"


def test_shift_list_detail_and_summaries(db, driver, driver_id):
    morning = day_shift(db, driver_id, "2026-10-01", start="08:00", end="12:00")
    evening = day_shift(db, driver_id, "2026-10-01", start="18:00", end="20:00")
    driver.post("/api/v1/trips", json={**TRIP, "shift_id": morning})
    driver.post(
        "/api/v1/trips",
        json={
            **TRIP,
            "id": tid("e1"),
            "shift_id": evening,
            "started_at": at("01T18:30"),
            "ended_at": at("01T19:00"),
            "fare": 1000,
            "commission_amount": 100,
            "payment_method": "cash",
        },
    )
    listed = driver.get("/api/v1/shifts", params={"work_date": "2026-10-01"}).json()
    assert [s["id"] for s in listed] == [morning, evening]
    m = listed[0]["summary"]
    assert (
        m["trips_count"],
        m["revenue"],
        m["net_income"],
        m["duration_minutes"],
        m["net_income_per_hour"],
    ) == (
        1,
        2400,
        2040,
        240,
        510,
    )

    detail = driver.get(f"/api/v1/shifts/{evening}").json()
    assert [t["id"] for t in detail["trips"]] == [tid("e1")]
    assert detail["summary"]["cash"] == {"trips_count": 1, "amount": 1000}

    day = driver.get("/api/v1/summary", params={"work_date": "2026-10-01"}).json()
    assert (day["shifts_count"], day["trips_count"], day["revenue"], day["net_income"]) == (2, 2, 3400, 2940)


def test_open_shift_summary_runs_up_to_now(driver):
    shift = driver.post("/api/v1/shifts", json={"started_at": at("03T10:00")}).json()
    assert shift["summary"]["duration_minutes"] == 120  # now is 12:00


# --- roles ---


def test_admins_have_no_shifts_of_their_own(app, db):
    create_driver(db, "admin@example.com", "horse-battery-9", role="admin")
    admin = logged_in(app, "admin@example.com")
    assert admin.get("/api/v1/shifts/current").status_code == 403
    assert admin.post("/api/v1/shifts", json={}).status_code == 403


def test_admin_reads_driver_shifts(app, db, driver, driver_id):
    shift = day_shift(db, driver_id)
    driver.post("/api/v1/trips", json={**TRIP, "shift_id": shift})
    create_driver(db, "admin@example.com", "horse-battery-9", role="admin")
    admin = logged_in(app, "admin@example.com")
    base = f"/api/v1/admin/drivers/{driver_id}/shifts"
    assert [s["id"] for s in admin.get(base, params={"work_date": "2026-10-01"}).json()] == [shift]
    assert len(admin.get(f"{base}/{shift}").json()["trips"]) == 1
    assert driver.get(base, params={"work_date": "2026-10-01"}).status_code == 403
