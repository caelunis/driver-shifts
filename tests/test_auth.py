import pytest
from fastapi.testclient import TestClient

from app.accounts import create_driver
from app.main import create_app

USER = {"email": "Driver@Example.com", "password": "secret-pass", "name": "Айдар"}


@pytest.fixture
def app(db):
    return create_app(db)


@pytest.fixture
def account(db):
    return create_driver(db, USER["email"], USER["password"], name=USER["name"])


@pytest.fixture
def client(app, account):
    """Client logged in as USER."""
    c = TestClient(app)
    assert login(c).status_code == 200
    return c


def login(client, email=USER["email"], password=USER["password"]):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- accounts are created by an admin, there is no self-registration ---

def test_self_registration_is_gone(app):
    r = TestClient(app).post("/api/auth/register", json={**USER, "email": "new@example.com"})
    assert r.status_code in (404, 405)


def test_login_returns_profile_with_role(app, account):
    r = login(TestClient(app))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "driver@example.com"  # normalized
    assert body["role"] == "driver"
    assert "password" not in str(body) and "hash" not in str(body)


def test_session_cookie_flags(app, account):
    cookie = login(TestClient(app)).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=2592000" in cookie  # 30 days


def test_email_is_unique_case_insensitive(db, account):
    from app.accounts import EmailTaken
    with pytest.raises(EmailTaken):
        create_driver(db, "DRIVER@example.com", "password123")


def test_password_is_stored_hashed(client, db):
    with db.connection() as conn:
        stored = conn.execute("SELECT password_hash FROM drivers").fetchone()["password_hash"]
    assert USER["password"] not in stored
    assert stored.startswith("scrypt$")


def test_session_token_is_stored_hashed(client, db):
    token = client.cookies["session"]
    with db.connection() as conn:
        stored = conn.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
    assert stored != token


# --- login / logout ---

def test_login_and_logout(app, account):
    fresh = TestClient(app)
    assert fresh.get("/api/me").status_code == 401
    assert login(fresh).status_code == 200
    assert fresh.get("/api/me").status_code == 200

    r = fresh.post("/api/auth/logout", json={})
    assert r.status_code == 204
    assert fresh.get("/api/me").status_code == 401


def test_logout_invalidates_session_server_side(client):
    token = client.cookies["session"]
    client.post("/api/auth/logout", json={})
    stolen = TestClient(client.app, cookies={"session": token})
    assert stolen.get("/api/me").status_code == 401


def test_wrong_password_and_unknown_email_look_the_same(app, account):
    wrong = login(TestClient(app), password="wrong-password")
    unknown = login(TestClient(app), email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_is_rate_limited_after_failures(app, account):
    other = TestClient(app)
    for _ in range(5):
        assert login(other, password="wrong-password").status_code == 401
    blocked = login(other)  # even the correct password is refused now
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_expired_session_is_rejected(client, db):
    with db.connection() as conn:
        conn.execute("UPDATE sessions SET expires_at = now() - interval '1 second'")
    assert client.get("/api/me").status_code == 401


def test_forged_cookie_is_rejected(app):
    assert TestClient(app, cookies={"session": "garbage"}).get("/api/me").status_code == 401


# --- CSRF ---

def test_form_encoded_login_is_rejected(app, account):
    r = TestClient(app).post(
        "/api/auth/login", data={"email": USER["email"], "password": USER["password"]}
    )
    assert r.status_code == 422


def test_logout_requires_json(client):
    assert client.post("/api/auth/logout").status_code == 415
    assert client.get("/api/me").status_code == 200


# --- profile: a driver may change only the timezone ---

def test_driver_changes_own_timezone(client):
    r = client.patch("/api/me", json={"default_tz": "+06:00"})
    assert r.status_code == 200
    assert r.json()["default_tz"] == "+06:00"
    assert client.get("/api/me").json()["default_tz"] == "+06:00"


@pytest.mark.parametrize("field, value", [
    ("name", "Другое имя"),
    ("car", "Toyota Camry"),
    ("default_commission_pct", 5),
    ("email", "evil@example.com"),
    ("password", "new-password"),
    ("role", "admin"),
])
def test_driver_cannot_change_admin_managed_fields(client, field, value):
    before = client.get("/api/me").json()
    r = client.patch("/api/me", json={field: value})
    assert r.status_code == 403
    assert r.json()["detail"]["fields"] == [field]
    assert client.get("/api/me").json() == before


def test_mixed_patch_is_rejected_as_a_whole(client):
    r = client.patch("/api/me", json={"default_tz": "+06:00", "car": "x"})
    assert r.status_code == 403
    assert client.get("/api/me").json()["default_tz"] == "+05:00"  # nothing applied


@pytest.mark.parametrize("value", ["+5", "+15:00", None, 5])
def test_timezone_validation(client, value):
    r = client.patch("/api/me", json={"default_tz": value})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "default_tz"]


def test_profile_requires_auth(app):
    anon = TestClient(app)
    assert anon.get("/api/me").status_code == 401
    assert anon.patch("/api/me", json={"default_tz": "+06:00"}).status_code == 401
