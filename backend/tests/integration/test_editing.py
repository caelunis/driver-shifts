"""Editing and deleting trips and shifts, by the driver (7-day window) and by the admin."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.trips import TripIn
from app.services.shifts import ShiftService
from app.services.trips import TripService
from tests.api import code, error, field_ctx, sid, tid
from tests.factories import create_driver, day_shift, set_commission_pct


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


@pytest.fixture
def admin(app, db):
    create_driver(db, "admin@example.com", "horse-battery-9", role="admin")
    return logged_in(app, "admin@example.com")


@pytest.fixture
def shift(db, driver_id):
    return day_shift(db, driver_id)  # 2026-10-01 00:00-23:59, id 1


def at(day_time: str) -> str:
    return f"2026-{day_time}:00+05:00"  # at("10-01T08:00") -> 2026-10-01T08:00:00+05:00


SHIFT_1 = sid(1)


def trip(shift_id=SHIFT_1, **overrides):
    return {
        "id": tid("t1"),
        "shift_id": shift_id,
        "started_at": at("10-01T08:10"),
        "ended_at": at("10-01T08:32"),
        "fare": 2400,
        "payment_method": "card",
        "commission_amount": 360,
        **overrides,
    }


# --- trips: commission ---


def test_new_amount_recomputes_commission_from_stored_percent(db, driver, driver_id, shift):
    set_commission_pct(db, driver_id, 15)
    r = driver.post("/api/v1/trips", json=trip(commission_amount=None))
    assert r.json()["commission_amount"] == 360 and r.json()["commission_percent"] == 15

    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 3000})
    assert r.status_code == 200
    assert r.json()["commission_amount"] == 450 and r.json()["commission_percent"] == 15


def test_later_profile_percent_does_not_touch_old_trips(db, driver, driver_id, shift):
    set_commission_pct(db, driver_id, 15)
    driver.post("/api/v1/trips", json=trip(commission_amount=None))
    set_commission_pct(db, driver_id, 20)

    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 3000})
    assert r.json()["commission_amount"] == 450  # 15% stored with the trip, not today's 20%


def test_commission_of_percent_trip_must_match(db, driver, driver_id, shift):
    set_commission_pct(db, driver_id, 15)
    driver.post("/api/v1/trips", json=trip(commission_amount=None))

    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 3000, "commission_amount": 100})
    assert r.status_code == 422 and error(r) == ("commission_amount", "commission_fixed")
    assert field_ctx(r)["expected"] == 450
    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 3000, "commission_amount": 450})
    assert r.status_code == 200


def test_hand_entered_commission_is_kept_and_checked(driver, shift):
    r = driver.post("/api/v1/trips", json=trip())
    assert r.json()["commission_percent"] is None

    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 3000})
    assert r.json()["commission_amount"] == 360  # entered by hand: left as it was

    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 300})
    assert r.status_code == 422 and error(r) == ("commission_amount", "commission_exceeds_fare")

    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 300, "commission_amount": 30})
    assert r.status_code == 200 and r.json()["commission_amount"] == 30


# --- trips: other fields ---


def test_edit_changes_summary(driver, shift):
    driver.post("/api/v1/trips", json=trip())
    driver.patch(f"/api/v1/trips/{tid('t1')}", json={"payment_method": "cash", "fare": 3000})
    s = driver.get("/api/v1/summary", params={"work_date": "2026-10-01"}).json()
    assert s["revenue"] == 3000 and s["cash"] == {"trips_count": 1, "amount": 3000}
    assert s["card"] == {"trips_count": 0, "amount": 0}


def test_empty_patch_returns_trip_unchanged(driver, shift):
    created = driver.post("/api/v1/trips", json=trip()).json()
    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={})
    assert r.status_code == 200 and r.json() == created


def test_end_checked_against_stored_start(driver, shift):
    driver.post("/api/v1/trips", json=trip())
    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"ended_at": at("10-01T08:00")})
    assert r.status_code == 422 and error(r) == ("ended_at", "end_before_start")


def test_trip_must_stay_inside_its_shift(db, driver, driver_id):
    day_shift(db, driver_id, start="08:00", end="12:00")
    driver.post("/api/v1/trips", json=trip())
    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"started_at": at("10-01T07:50")})
    assert r.status_code == 422 and error(r) == ("started_at", "outside_shift")


def test_move_trip_to_another_shift(db, driver, driver_id, shift):
    other = day_shift(db, driver_id, day="2026-10-02")
    driver.post("/api/v1/trips", json=trip())

    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"shift_id": other})
    assert r.status_code == 422 and error(r) == ("started_at", "outside_shift")  # times are on 10-01

    r = driver.patch(
        f"/api/v1/trips/{tid('t1')}",
        json={"shift_id": other, "started_at": at("10-02T08:10"), "ended_at": at("10-02T08:32")},
    )
    assert r.status_code == 200 and r.json()["shift_id"] == other
    assert driver.get("/api/v1/trips", params={"work_date": "2026-10-01"}).json() == []
    assert len(driver.get("/api/v1/trips", params={"work_date": "2026-10-02"}).json()) == 1


def test_cannot_move_trip_to_someone_elses_shift(db, driver, shift):
    bob = create_driver(db, "bob@example.com", "horse-battery-9")
    bobs_shift = day_shift(db, bob, day="2026-10-02")
    driver.post("/api/v1/trips", json=trip())
    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"shift_id": bobs_shift})
    assert r.status_code == 422 and error(r) == ("shift_id", "shift_not_found")


@pytest.mark.parametrize(
    "body, expected",
    [
        ({"fare": None}, ("fare", "null_not_allowed")),
        ({"id": tid("t2")}, ("id", "extra_forbidden")),
        ({"fare": 0}, ("fare", "greater_than")),
    ],
)
def test_patch_body_validation(driver, shift, body, expected):
    driver.post("/api/v1/trips", json=trip())
    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json=body)
    assert r.status_code == 422 and error(r) == expected


def test_resending_original_after_edit_is_a_conflict(driver, shift):
    body = trip(id=None)
    trip_id = driver.post("/api/v1/trips", json=body).json()["id"]
    driver.patch(f"/api/v1/trips/{trip_id}", json={"fare": 3000})
    # A retry of the original request must not create a second copy of the trip
    r = driver.post("/api/v1/trips", json=body)
    assert r.status_code == 409
    assert len(driver.get("/api/v1/trips", params={"work_date": "2026-10-01"}).json()) == 1


def test_delete_trip(driver, shift):
    driver.post("/api/v1/trips", json=trip())
    assert driver.delete(f"/api/v1/trips/{tid('t1')}").status_code == 204
    assert driver.delete(f"/api/v1/trips/{tid('t1')}").status_code == 404
    assert driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 1}).status_code == 404
    assert driver.get("/api/v1/summary", params={"work_date": "2026-10-01"}).json()["trips_count"] == 0


def test_other_drivers_trip_is_not_found(app, db, driver, shift):
    driver.post("/api/v1/trips", json=trip())
    create_driver(db, "bob@example.com", "horse-battery-9")
    bob = logged_in(app, "bob@example.com")
    assert bob.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 3000}).status_code == 404
    assert bob.delete(f"/api/v1/trips/{tid('t1')}").status_code == 404
    assert driver.get("/api/v1/trips", params={"work_date": "2026-10-01"}).json()[0]["fare"] == 2400


# --- the 7-day window ---


@pytest.fixture
def old_trip(db, driver_id):
    """A trip in a shift that ended on 2026-09-20, more than 7 days before "now"."""
    old = day_shift(db, driver_id, day="2026-09-20")
    db.service(TripService).add(
        driver_id,
        TripIn(**trip(shift_id=old, started_at=at("09-20T08:10"), ended_at=at("09-20T08:32"))),
        by_admin=True,
    )
    return old


def test_driver_cannot_change_trips_of_old_shift(driver, old_trip):
    r = driver.patch(f"/api/v1/trips/{tid('t1')}", json={"fare": 3000})
    assert r.status_code == 409 and code(r) == "shift_locked"
    r = driver.delete(f"/api/v1/trips/{tid('t1')}")
    assert r.status_code == 409 and code(r) == "shift_locked"


def test_driver_cannot_move_trip_into_old_shift(db, driver, driver_id, shift):
    old = day_shift(db, driver_id, day="2026-09-20")
    driver.post("/api/v1/trips", json=trip())
    r = driver.patch(
        f"/api/v1/trips/{tid('t1')}",
        json={"shift_id": old, "started_at": at("09-20T08:10"), "ended_at": at("09-20T08:32")},
    )
    assert r.status_code == 422 and error(r) == ("shift_id", "too_old")


def test_driver_cannot_change_old_shift(driver, old_trip):
    r = driver.patch(f"/api/v1/shifts/{old_trip}", json={"note": "x"})
    assert r.status_code == 409 and code(r) == "shift_locked"
    r = driver.delete(f"/api/v1/shifts/{old_trip}")
    assert r.status_code == 409 and code(r) == "shift_locked"


def test_shift_within_window_is_editable(db, driver, driver_id):
    # Ended 2026-09-26 23:59, 6.5 days before "now"
    s = day_shift(db, driver_id, day="2026-09-26")
    assert driver.patch(f"/api/v1/shifts/{s}", json={"note": "ok"}).status_code == 200


def test_admin_edits_without_limit(admin, driver_id, old_trip):
    base = f"/api/v1/admin/drivers/{driver_id}"
    r = admin.patch(f"{base}/trips/{tid('t1')}", json={"fare": 3000})
    assert r.status_code == 200 and r.json()["fare"] == 3000
    r = admin.patch(
        f"{base}/shifts/{old_trip}", json={"started_at": at("09-19T20:00"), "ended_at": at("09-20T12:00")}
    )
    assert r.status_code == 200 and r.json()["work_date"] == "2026-09-19"
    assert admin.delete(f"{base}/trips/{tid('t1')}").status_code == 204
    assert admin.delete(f"{base}/shifts/{old_trip}").status_code == 204
    assert admin.get(f"{base}/days").json() == []


def test_admin_cannot_reach_other_drivers_entries_through_wrong_path(db, admin, driver_id, shift):
    bob = create_driver(db, "bob@example.com", "horse-battery-9")
    assert admin.patch(f"/api/v1/admin/drivers/{bob}/shifts/{shift}", json={"note": "x"}).status_code == 404
    assert admin.delete(f"/api/v1/admin/drivers/{bob}/shifts/{shift}").status_code == 404


def test_driver_cannot_use_admin_edit_endpoints(driver, driver_id, shift):
    r = driver.patch(f"/api/v1/admin/drivers/{driver_id}/shifts/{shift}", json={"note": "x"})
    assert r.status_code == 403


# --- shifts ---


def test_edit_note_and_times(driver, shift):
    r = driver.patch(
        f"/api/v1/shifts/{shift}",
        json={"note": "Аэропорт", "started_at": at("09-30T22:00"), "ended_at": at("10-01T10:00")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["note"] == "Аэропорт" and body["work_date"] == "2026-09-30"
    assert body["summary"]["duration_minutes"] == 12 * 60
    # The day of the shift moved, and its trips with it
    assert driver.get("/api/v1/shifts", params={"work_date": "2026-10-01"}).json() == []


def test_shift_must_keep_its_trips_inside(driver, shift):
    driver.post("/api/v1/trips", json=trip())  # 08:10-08:32
    r = driver.patch(f"/api/v1/shifts/{shift}", json={"started_at": at("10-01T08:20")})
    assert r.status_code == 422 and error(r) == ("started_at", "after_first_trip")
    r = driver.patch(f"/api/v1/shifts/{shift}", json={"ended_at": at("10-01T08:20")})
    assert r.status_code == 422 and error(r) == ("ended_at", "before_last_trip")
    r = driver.patch(
        f"/api/v1/shifts/{shift}", json={"started_at": at("10-01T08:10"), "ended_at": at("10-01T08:32")}
    )
    assert r.status_code == 200


@pytest.mark.parametrize(
    "body, expected",
    [
        ({"ended_at": "2026-10-01T00:00:00+05:00"}, ("ended_at", "end_before_start")),
        ({"started_at": "2026-09-30T23:00:00+05:00"}, ("ended_at", "shift_too_long")),
        (
            {"ended_at": "2026-10-03T12:30:00+05:00", "started_at": "2026-10-03T08:00:00+05:00"},
            ("ended_at", "in_future"),
        ),
        (
            {"started_at": "2026-09-25T08:00:00+05:00", "ended_at": "2026-09-25T10:00:00+05:00"},
            ("started_at", "too_old"),
        ),
        ({"started_at": None}, ("started_at", "null_not_allowed")),
        ({"note": "x" * 501}, ("note", "string_too_long")),
        ({"driver_id": 2}, ("driver_id", "extra_forbidden")),
    ],
)
def test_shift_patch_validation(driver, shift, body, expected):
    r = driver.patch(f"/api/v1/shifts/{shift}", json=body)
    assert r.status_code == 422 and error(r) == expected


def test_shifts_cannot_overlap_after_edit(db, driver, driver_id, shift):
    other = day_shift(db, driver_id, day="2026-10-02")
    r = driver.patch(
        f"/api/v1/shifts/{other}", json={"started_at": at("10-01T23:00"), "ended_at": at("10-02T08:00")}
    )
    assert r.status_code == 409 and code(r) == "shift_overlap"


def test_reopen_latest_shift(db, driver, driver_id):
    s = day_shift(db, driver_id, day="2026-10-03", start="06:00", end="10:00")
    r = driver.patch(f"/api/v1/shifts/{s}", json={"ended_at": None})
    assert r.status_code == 200 and r.json()["status"] == "open"
    assert driver.get("/api/v1/shifts/current").json()["id"] == s


def test_cannot_reopen_shift_older_than_24_hours(driver, shift):
    r = driver.patch(f"/api/v1/shifts/{shift}", json={"ended_at": None})  # started 60 h ago
    assert r.status_code == 422 and error(r) == ("ended_at", "shift_too_long")


def test_only_latest_shift_can_be_reopened(db, driver, driver_id):
    earlier = day_shift(db, driver_id, day="2026-10-02", start="20:00", end="23:00")
    day_shift(db, driver_id, day="2026-10-03", start="06:00", end="10:00")
    # Open, it would extend over the later shift
    r = driver.patch(f"/api/v1/shifts/{earlier}", json={"ended_at": None})
    assert r.status_code == 409 and code(r) == "shift_overlap"


def test_cannot_reopen_while_another_shift_is_open(db, driver, driver_id):
    s = day_shift(db, driver_id, day="2026-10-03", start="06:00", end="10:00")
    driver.post("/api/v1/shifts", json={})  # open since 12:00
    r = driver.patch(f"/api/v1/shifts/{s}", json={"ended_at": None})
    assert r.status_code == 409 and code(r) == "shift_already_open"


def test_delete_shift_with_its_trips(db, driver, shift):
    driver.post("/api/v1/trips", json=trip())
    assert driver.delete(f"/api/v1/shifts/{shift}").status_code == 204
    assert driver.get(f"/api/v1/shifts/{shift}").status_code == 404
    assert driver.get("/api/v1/days").json() == []
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"] == 0


def test_other_drivers_shift_is_not_found(app, db, driver, shift):
    create_driver(db, "bob@example.com", "horse-battery-9")
    bob = logged_in(app, "bob@example.com")
    assert bob.patch(f"/api/v1/shifts/{shift}", json={"note": "x"}).status_code == 404
    assert bob.delete(f"/api/v1/shifts/{shift}").status_code == 404


# --- concurrency ---


def test_concurrent_trip_and_shift_edits_do_not_deadlock(db, driver_id, shift):
    other = day_shift(db, driver_id, day="2026-10-02")
    db.service(TripService).add(driver_id, TripIn(**trip()))

    driver, shifts = UUID(driver_id), [UUID(shift), UUID(other)]

    def move(i):
        day = "10-02" if i % 2 else "10-01"
        db.service(TripService).update(
            driver,
            UUID(tid("t1")),
            {
                "shift_id": shifts[i % 2],
                "started_at": datetime.fromisoformat(at(f"{day}T08:10")),
                "ended_at": datetime.fromisoformat(at(f"{day}T08:32")),
            },
        )

    def touch_shifts(i):
        db.service(ShiftService).update(driver, shifts[(i + 1) % 2], {"note": str(i)})

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(f, i) for i in range(20) for f in (move, touch_shifts)]
        errors = [f.exception() for f in futures if f.exception() is not None]
    # Domain conflicts are fine; deadlocks or other database errors are not
    assert all(type(e).__name__ in ("ConflictError", "DomainValidationError") for e in errors), errors
