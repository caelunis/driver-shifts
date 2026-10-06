import pytest
from fastapi.testclient import TestClient

from app.accounts import create_driver
from app.main import create_app

TRIP = {"id": "t1", "start": "2026-10-01T08:10:00+05:00", "end": "2026-10-01T08:32:00+05:00",
        "amount": 2400, "payment": "card", "commission": 360}
DAY = {"date": "2026-10-01"}
NEW_DRIVER = {"email": "Erlan@Example.com", "password": "temp-pass-1", "name": " Ерлан ",
              "car": "Hyundai Accent 777 AAA 02", "default_commission_pct": 15}


@pytest.fixture
def app(db):
    return create_app(db)


def logged_in(app, email, password):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200
    return c


@pytest.fixture
def admin_id(db):
    return create_driver(db, "admin@example.com", "admin-pass", name="Админ", role="admin")


@pytest.fixture
def admin(app, admin_id):
    return logged_in(app, "admin@example.com", "admin-pass")


@pytest.fixture
def driver_id(db):
    return create_driver(db, "driver@example.com", "driver-pass", name="Айдар")


@pytest.fixture
def driver(app, driver_id):
    return logged_in(app, "driver@example.com", "driver-pass")


def count(db, table):
    with db.connection() as conn:
        return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


# --- access matrix ---

ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/drivers", {}),
    ("POST", "/api/admin/drivers", {"json": NEW_DRIVER}),
    ("GET", "/api/admin/drivers/{id}", {}),
    ("PATCH", "/api/admin/drivers/{id}", {"json": {"car": "x"}}),
    ("DELETE", "/api/admin/drivers/{id}", {}),
    ("GET", "/api/admin/drivers/{id}/days", {}),
    ("GET", "/api/admin/drivers/{id}/trips", {"params": DAY}),
    ("GET", "/api/admin/drivers/{id}/summary", {"params": DAY}),
]


@pytest.mark.parametrize("method, path, kwargs", ADMIN_ENDPOINTS)
def test_admin_endpoints_are_forbidden_for_drivers(db, driver, driver_id, method, path, kwargs):
    r = driver.request(method, path.format(id=driver_id), **kwargs)
    assert r.status_code == 403
    assert count(db, "drivers") == 1  # nothing created or deleted


@pytest.mark.parametrize("method, path, kwargs", ADMIN_ENDPOINTS)
def test_admin_endpoints_require_auth(app, driver_id, method, path, kwargs):
    assert TestClient(app).request(method, path.format(id=driver_id), **kwargs).status_code == 401


@pytest.mark.parametrize("method, path, kwargs", [
    ("GET", "/api/days", {}),
    ("GET", "/api/trips", {"params": DAY}),
    ("GET", "/api/summary", {"params": DAY}),
    ("POST", "/api/trips", {"json": TRIP}),
    ("PATCH", "/api/me", {"json": {"default_tz": "+06:00"}}),
])
def test_admin_has_no_diary_of_their_own(db, admin, method, path, kwargs):
    assert admin.request(method, path, **kwargs).status_code == 403
    assert count(db, "trips") == 0


def test_admin_sees_own_profile_with_role(admin):
    assert admin.get("/api/me").json()["role"] == "admin"


# --- listing and search ---

def test_list_shows_drivers_with_totals_but_not_admins(admin, driver):
    driver.post("/api/trips", json=TRIP)
    driver.post("/api/trips", json={**TRIP, "id": "t2", "start": "2026-10-03T10:00:00+05:00",
                                    "end": "2026-10-03T10:20:00+05:00", "amount": 1000,
                                    "commission": 100})
    [row] = admin.get("/api/admin/drivers").json()
    assert row["email"] == "driver@example.com"
    assert (row["trips_count"], row["revenue"], row["net"]) == (2, 3400, 2940)
    assert row["last_trip_day"] == "2026-10-03"


def test_driver_without_trips_has_zero_totals(admin, driver_id):
    [row] = admin.get("/api/admin/drivers").json()
    assert (row["trips_count"], row["revenue"], row["net"], row["last_trip_day"]) == (0, 0, 0, None)


@pytest.mark.parametrize("q, expected", [
    ("айдар", ["Айдар"]),           # name, case-insensitive
    ("BOLAT@", ["Болат"]),           # email
    ("camry", ["Айдар"]),           # car
    ("  ", ["Айдар", "Болат"]),      # blank query = everyone
    ("%", []),                       # LIKE wildcards are taken literally
    ("_", []),
])
def test_search(db, admin, q, expected):
    a = create_driver(db, "aidar@example.com", "password123", name="Айдар")
    create_driver(db, "bolat@example.com", "password123", name="Болат")
    admin.patch(f"/api/admin/drivers/{a}", json={"car": "Toyota Camry"})
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
    assert body["car"] == NEW_DRIVER["car"]
    assert body["default_commission_pct"] == 15
    assert body["default_tz"] == "+05:00"
    assert "password" not in str(body) and "hash" not in str(body)

    new = logged_in(app, "erlan@example.com", "temp-pass-1")
    assert new.get("/api/me").json()["id"] == body["id"]


def test_create_driver_with_taken_email(admin, driver_id):
    r = admin.post("/api/admin/drivers", json={**NEW_DRIVER, "email": "DRIVER@example.com"})
    assert r.status_code == 409


def test_create_cannot_make_an_admin(admin):
    body = admin.post("/api/admin/drivers", json={**NEW_DRIVER, "role": "admin"}).json()
    assert body["role"] == "driver"


@pytest.mark.parametrize("patch, field", [
    ({"email": "nope"}, "email"),
    ({"password": "short"}, "password"),
    ({"name": "   "}, "name"),
    ({"default_commission_pct": 100}, "default_commission_pct"),
    ({"default_commission_pct": -1}, "default_commission_pct"),
    ({"default_tz": "+5"}, "default_tz"),
])
def test_create_validation(db, admin, patch, field):
    r = admin.post("/api/admin/drivers", json={**NEW_DRIVER, **patch})
    assert r.status_code == 422
    assert [e["loc"][-1] for e in r.json()["detail"]] == [field]
    assert count(db, "drivers") == 1  # only the admin


# --- update ---

def test_admin_updates_driver(admin, driver, driver_id):
    r = admin.patch(f"/api/admin/drivers/{driver_id}",
                    json={"name": "Айдар Б.", "car": "Kia Rio", "default_commission_pct": 12.5})
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["car"], r.json()["default_commission_pct"]) == \
           ("Айдар Б.", "Kia Rio", 12.5)
    assert driver.get("/api/me").json()["car"] == "Kia Rio"  # the driver sees it

    cleared = admin.patch(f"/api/admin/drivers/{driver_id}", json={"default_commission_pct": None})
    assert cleared.json()["default_commission_pct"] is None


def test_password_change_ends_driver_sessions(app, admin, driver, driver_id):
    assert admin.patch(f"/api/admin/drivers/{driver_id}",
                       json={"password": "brand-new-pass"}).status_code == 200
    assert driver.get("/api/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={
        "email": "driver@example.com", "password": "driver-pass"}).status_code == 401
    logged_in(app, "driver@example.com", "brand-new-pass")


def test_profile_change_keeps_driver_sessions(admin, driver, driver_id):
    admin.patch(f"/api/admin/drivers/{driver_id}", json={"car": "Kia Rio"})
    assert driver.get("/api/me").status_code == 200


def test_update_cannot_change_email_or_role(admin, driver_id):
    body = admin.patch(f"/api/admin/drivers/{driver_id}",
                       json={"email": "x@example.com", "role": "admin"}).json()
    assert (body["email"], body["role"]) == ("driver@example.com", "driver")


@pytest.mark.parametrize("patch", [{"name": None}, {"car": None}, {"default_tz": None},
                                   {"password": None}, {"password": "short"}])
def test_update_validation(admin, driver_id, patch):
    assert admin.patch(f"/api/admin/drivers/{driver_id}", json=patch).status_code == 422


# --- delete ---

def test_admin_deletes_driver_with_trips_and_sessions(db, admin, driver, driver_id):
    driver.post("/api/trips", json=TRIP)
    other = create_driver(db, "other@example.com", "password123")

    assert admin.delete(f"/api/admin/drivers/{driver_id}").status_code == 204

    assert driver.get("/api/me").status_code == 401
    assert count(db, "trips") == 0
    assert [d["id"] for d in admin.get("/api/admin/drivers").json()] == [other]
    assert admin.get(f"/api/admin/drivers/{driver_id}").status_code == 404


@pytest.mark.parametrize("method, kwargs", [
    ("GET", {}), ("PATCH", {"json": {"name": "x"}}), ("DELETE", {}),
])
def test_admins_are_not_reachable_through_driver_api(db, admin, admin_id, method, kwargs):
    other_admin = create_driver(db, "admin2@example.com", "password123", role="admin")
    for target in (admin_id, other_admin):  # self and another admin
        assert admin.request(method, f"/api/admin/drivers/{target}", **kwargs).status_code == 404
    assert count(db, "drivers") == 2


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
