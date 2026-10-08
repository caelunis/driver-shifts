import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.api import code, error, fields
from tests.factories import create_driver, day_shift

# shift_id 1: the day shift created by the `driver` fixture
TRIP = {
    "id": "t1",
    "shift_id": 1,
    "start": "2026-10-01T08:10:00+05:00",
    "end": "2026-10-01T08:32:00+05:00",
    "amount": 2400,
    "payment": "card",
    "commission": 360,
}
DAY = {"date": "2026-10-01"}
NEW_DRIVER = {
    "email": "Erlan@Example.com",
    "password": "temp-pass-1",
    "name": " Ерлан ",
    "car_model": "Hyundai Accent",
    "car_plate": "777 aaa 02",
    "default_commission_pct": 15,
}


@pytest.fixture
def app(db):
    return create_app(db.database)


def logged_in(app, email, password):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200
    return c


@pytest.fixture
def admin_id(db):
    return create_driver(db, "admin@example.com", "admin-pass-1", name="Админ", role="admin")


@pytest.fixture
def admin(app, admin_id):
    return logged_in(app, "admin@example.com", "admin-pass-1")


@pytest.fixture
def driver_id(db):
    return create_driver(db, "driver@example.com", "driver-pass-1", name="Айдар")


@pytest.fixture
def driver(app, db, driver_id):
    assert day_shift(db, driver_id) == 1  # the shift TRIP goes into
    return logged_in(app, "driver@example.com", "driver-pass-1")


def count(db, table):
    with db.connection() as conn:
        return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


# --- access matrix ---

ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/drivers", {}),
    ("POST", "/api/admin/drivers", {"json": NEW_DRIVER}),
    ("GET", "/api/admin/drivers/{id}", {}),
    ("PATCH", "/api/admin/drivers/{id}", {"json": {"car_model": "x"}}),
    ("DELETE", "/api/admin/drivers/{id}", {}),
    ("GET", "/api/admin/drivers/{id}/days", {}),
    ("GET", "/api/admin/drivers/{id}/trips", {"params": DAY}),
    ("GET", "/api/admin/drivers/{id}/summary", {"params": DAY}),
]


@pytest.mark.parametrize("method, path, kwargs", ADMIN_ENDPOINTS)
def test_admin_endpoints_are_forbidden_for_drivers(db, driver, driver_id, method, path, kwargs):
    r = driver.request(method, path.format(id=driver_id), **kwargs)
    assert r.status_code == 403
    assert count(db, "users") == 1  # nothing created or deleted


@pytest.mark.parametrize("method, path, kwargs", ADMIN_ENDPOINTS)
def test_admin_endpoints_require_auth(app, driver_id, method, path, kwargs):
    assert TestClient(app).request(method, path.format(id=driver_id), **kwargs).status_code == 401


@pytest.mark.parametrize(
    "method, path, kwargs",
    [
        ("GET", "/api/days", {}),
        ("GET", "/api/trips", {"params": DAY}),
        ("GET", "/api/summary", {"params": DAY}),
        ("POST", "/api/trips", {"json": TRIP}),
        ("PATCH", "/api/me", {"json": {"default_tz": "Asia/Aqtau"}}),
    ],
)
def test_admin_has_no_diary_of_their_own(db, admin, method, path, kwargs):
    assert admin.request(method, path, **kwargs).status_code == 403
    assert count(db, "trips") == 0


def test_admin_sees_own_profile_with_role(admin):
    assert admin.get("/api/me").json()["role"] == "admin"


# --- listing and search ---


def test_list_shows_drivers_with_totals_but_not_admins(db, admin, driver, driver_id):
    driver.post("/api/trips", json=TRIP)
    second = day_shift(db, driver_id, "2026-10-03", end="11:00")  # "now" is 10-03 12:00
    driver.post(
        "/api/trips",
        json={
            **TRIP,
            "id": "t2",
            "shift_id": second,
            "start": "2026-10-03T10:00:00+05:00",
            "end": "2026-10-03T10:20:00+05:00",
            "amount": 1000,
            "commission": 100,
        },
    )
    [row] = admin.get("/api/admin/drivers").json()
    assert row["email"] == "driver@example.com"
    assert (row["trips_count"], row["revenue"], row["net"]) == (2, 3400, 2940)
    assert row["last_trip_day"] == "2026-10-03"


def test_driver_without_trips_has_zero_totals(admin, driver_id):
    [row] = admin.get("/api/admin/drivers").json()
    assert (row["trips_count"], row["revenue"], row["net"], row["last_trip_day"]) == (0, 0, 0, None)


@pytest.mark.parametrize(
    "q, expected",
    [
        ("айдар", ["Айдар"]),  # name, case-insensitive
        ("BOLAT@", ["Болат"]),  # email
        ("camry", ["Айдар"]),  # car model
        ("123 abc", ["Айдар"]),  # plate, typed with spaces
        ("  ", ["Айдар", "Болат"]),  # blank query = everyone
        ("%", []),  # LIKE wildcards are taken literally
        ("_", []),
    ],
)
def test_search(db, admin, q, expected):
    a = create_driver(db, "aidar@example.com", "horse-battery-9", name="Айдар")
    create_driver(db, "bolat@example.com", "horse-battery-9", name="Болат")
    admin.patch(f"/api/admin/drivers/{a}", json={"car_model": "Toyota Camry", "car_plate": "123ABC02"})
    names = [d["name"] for d in admin.get("/api/admin/drivers", params={"q": q}).json()]
    assert names == expected


# --- create ---


def test_admin_creates_driver_who_can_log_in(app, admin):
    r = admin.post("/api/admin/drivers", json=NEW_DRIVER)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "erlan@example.com"
    assert body["name"] == "Ерлан"
    assert body["role"] == "driver"
    assert (body["car_model"], body["car_plate"]) == ("Hyundai Accent", "777AAA02")
    assert body["default_commission_pct"] == 15
    assert body["default_tz"] == "Asia/Almaty"
    assert "password" not in str(body) and "hash" not in str(body)

    new = logged_in(app, "erlan@example.com", "temp-pass-1")
    assert new.get("/api/me").json()["id"] == body["id"]


def test_create_driver_with_taken_email(admin, driver_id):
    r = admin.post("/api/admin/drivers", json={**NEW_DRIVER, "email": "DRIVER@example.com"})
    assert r.status_code == 409


def test_create_cannot_make_an_admin(db, admin):
    r = admin.post("/api/admin/drivers", json={**NEW_DRIVER, "role": "admin"})
    assert r.status_code == 422 and error(r) == ("role", "extra_forbidden")
    assert count(db, "users") == 1


@pytest.mark.parametrize(
    "patch, field",
    [
        ({"email": "nope"}, "email"),
        ({"password": "short"}, "password"),
        ({"name": "   "}, "name"),
        ({"default_commission_pct": 100}, "default_commission_pct"),
        ({"default_commission_pct": -1}, "default_commission_pct"),
        ({"default_tz": "+05:00"}, "default_tz"),
        ({"car_plate": "A123BC"}, "car_plate"),
        ({"car_plate": "123ABC21"}, "car_plate"),  # no such region
        ({"name": "12345"}, "name"),
        ({"name": "Ерлан\u200b"}, "name"),  # zero-width space
        ({"car_model": "Kia\nRio"}, "car_model"),
        ({"password": "erlan@example.com"}, "password"),
        ({"password": "qwerty123"}, "password"),
    ],
)
def test_create_validation(db, admin, patch, field):
    r = admin.post("/api/admin/drivers", json={**NEW_DRIVER, **patch})
    assert r.status_code == 422
    assert list(fields(r)) == [field]
    assert count(db, "users") == 1  # only the admin


# --- update ---


def test_admin_updates_driver(admin, driver, driver_id):
    r = admin.patch(
        f"/api/admin/drivers/{driver_id}",
        json={"name": "  Айдар   Б. ", "car_model": "Kia Rio", "default_commission_pct": 12.5},
    )
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["car_model"], r.json()["default_commission_pct"]) == (
        "Айдар Б.",
        "Kia Rio",
        12.5,
    )
    assert driver.get("/api/me").json()["car_model"] == "Kia Rio"  # the driver sees it

    cleared = admin.patch(f"/api/admin/drivers/{driver_id}", json={"default_commission_pct": None})
    assert cleared.json()["default_commission_pct"] is None


def test_password_change_ends_driver_sessions(app, admin, driver, driver_id):
    assert (
        admin.patch(f"/api/admin/drivers/{driver_id}", json={"password": "brand-new-pass-1"}).status_code
        == 200
    )
    assert driver.get("/api/me").status_code == 401
    assert (
        TestClient(app)
        .post("/api/auth/login", json={"email": "driver@example.com", "password": "driver-pass-1"})
        .status_code
        == 401
    )
    logged_in(app, "driver@example.com", "brand-new-pass-1")


def test_profile_change_keeps_driver_sessions(admin, driver, driver_id):
    admin.patch(f"/api/admin/drivers/{driver_id}", json={"car_model": "Kia Rio"})
    assert driver.get("/api/me").status_code == 200


def test_update_cannot_change_email_or_role(admin, driver_id):
    r = admin.patch(f"/api/admin/drivers/{driver_id}", json={"email": "x@example.com", "role": "admin"})
    assert r.status_code == 422
    assert fields(r) == {"email": "extra_forbidden", "role": "extra_forbidden"}
    body = admin.get(f"/api/admin/drivers/{driver_id}").json()
    assert (body["email"], body["role"]) == ("driver@example.com", "driver")


def test_plate_is_unique(db, admin, driver_id):
    assert admin.post("/api/admin/drivers", json=NEW_DRIVER).status_code == 201
    r = admin.patch(f"/api/admin/drivers/{driver_id}", json={"car_plate": "777АAA02"})  # Cyrillic А
    assert r.status_code == 409 and code(r) == "plate_taken"
    r = admin.post("/api/admin/drivers", json={**NEW_DRIVER, "email": "x@example.com"})
    assert r.status_code == 409 and code(r) == "plate_taken"
    assert count(db, "users") == 3  # admin, driver, Erlan: the failed create left nothing


def test_plate_can_be_removed(admin, driver_id):
    admin.patch(f"/api/admin/drivers/{driver_id}", json={"car_plate": "123ABC02"})
    r = admin.patch(f"/api/admin/drivers/{driver_id}", json={"car_plate": None})
    assert r.status_code == 200 and r.json()["car_plate"] is None


def test_new_password_must_differ_from_email(db, admin):
    # An address with digits, so that the password passes the letter-and-digit rule
    # and it is the email check that rejects it
    other = create_driver(db, "erlan2026@example.com", "horse-battery-9")
    for password in ("Erlan2026@Example.com", "erlan2026"):
        r = admin.patch(f"/api/admin/drivers/{other}", json={"password": password})
        assert r.status_code == 422 and error(r) == ("password", "password_like_email")


@pytest.mark.parametrize("password", ["onlyletters", "12345678901", "--------!!"])
def test_password_needs_a_letter_and_a_digit(admin, driver_id, password):
    r = admin.patch(f"/api/admin/drivers/{driver_id}", json={"password": password})
    assert r.status_code == 422 and error(r) == ("password", "password_too_weak")


def test_password_letters_may_be_cyrillic(admin, driver_id):
    r = admin.patch(f"/api/admin/drivers/{driver_id}", json={"password": "пароль-для-такси-7"})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "patch",
    [{"name": None}, {"car_model": None}, {"default_tz": None}, {"password": None}, {"password": "short"}],
)
def test_update_validation(admin, driver_id, patch):
    assert admin.patch(f"/api/admin/drivers/{driver_id}", json=patch).status_code == 422


# --- delete ---


def test_admin_deletes_driver_with_trips_and_sessions(db, admin, driver, driver_id):
    driver.post("/api/trips", json=TRIP)
    other = create_driver(db, "other@example.com", "horse-battery-9")

    assert admin.delete(f"/api/admin/drivers/{driver_id}").status_code == 204

    assert driver.get("/api/me").status_code == 401
    assert count(db, "trips") == 0
    assert [d["id"] for d in admin.get("/api/admin/drivers").json()] == [other]
    assert admin.get(f"/api/admin/drivers/{driver_id}").status_code == 404


@pytest.mark.parametrize(
    "method, kwargs",
    [
        ("GET", {}),
        ("PATCH", {"json": {"name": "x"}}),
        ("DELETE", {}),
    ],
)
def test_admins_are_not_reachable_through_driver_api(db, admin, admin_id, method, kwargs):
    other_admin = create_driver(db, "admin2@example.com", "horse-battery-9", role="admin")
    for target in (admin_id, other_admin):  # self and another admin
        assert admin.request(method, f"/api/admin/drivers/{target}", **kwargs).status_code == 404
    assert count(db, "users") == 2  # both admins still there


def test_unknown_driver_is_404(admin):
    assert admin.get("/api/admin/drivers/999999").status_code == 404
    assert admin.delete("/api/admin/drivers/999999").status_code == 404


# --- read-only diary of a driver ---


def test_admin_reads_driver_diary(admin, driver, driver_id):
    driver.post("/api/trips", json=TRIP)
    base = f"/api/admin/drivers/{driver_id}"
    assert admin.get(f"{base}/days").json() == [{"date": "2026-10-01", "count": 1, "net": 2040}]
    [trip] = admin.get(f"{base}/trips", params=DAY).json()
    assert trip["start"] == "2026-10-01T08:10:00+05:00"
    assert admin.get(f"{base}/summary", params=DAY).json()["revenue"] == 2400


def test_admin_diary_view_is_read_only(admin, driver_id):
    r = admin.post(f"/api/admin/drivers/{driver_id}/trips", json=TRIP)
    assert r.status_code == 405


@pytest.mark.parametrize(
    "patch, expected",
    [
        ({"name": "   "}, ("name", "blank")),
        ({"name": "Е" * 101}, ("name", "string_too_long")),
        ({"car_model": "K" * 101}, ("car_model", "string_too_long")),
    ],
)
def test_text_field_error_codes(admin, patch, expected):
    r = admin.post("/api/admin/drivers", json={**NEW_DRIVER, **patch})
    assert r.status_code == 422 and error(r) == expected
