import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

USER = {"email": "Driver@Example.com", "password": "secret-pass", "name": "  Айдар  "}


@pytest.fixture
def client(db):
    return TestClient(create_app(db))


def register(client, **overrides):
    return client.post("/api/auth/register", json={**USER, **overrides})


def login(client, email=USER["email"], password=USER["password"]):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- registration ---

def test_register_creates_account_and_logs_in(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "driver@example.com"  # normalized
    assert body["name"] == "Айдар"                # trimmed
    assert body["default_tz"] == "+05:00"
    assert "password" not in json.dumps(body) and "hash" not in json.dumps(body)
    assert client.get("/api/me").json()["id"] == body["id"]


def test_session_cookie_flags(client):
    cookie = register(client).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=2592000" in cookie  # 30 days


def test_email_is_unique_case_insensitive(client):
    register(client)
    r = register(TestClient(client.app), email="DRIVER@example.com")
    assert r.status_code == 409


@pytest.mark.parametrize("patch, field", [
    ({"email": "not-an-email"}, "email"),
    ({"password": "short"}, "password"),
    ({"name": "   "}, "name"),
])
def test_register_validation(client, patch, field):
    r = register(client, **patch)
    assert r.status_code == 422
    assert [e["loc"][-1] for e in r.json()["detail"]] == [field]


def test_password_is_stored_hashed(client, db):
    register(client)
    with db.connection() as conn:
        stored = conn.execute("SELECT password_hash FROM drivers").fetchone()["password_hash"]
    assert USER["password"] not in stored
    assert stored.startswith("scrypt$")


def test_session_token_is_stored_hashed(client, db):
    register(client)
    token = client.cookies["session"]
    with db.connection() as conn:
        stored = conn.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
    assert stored != token


# --- login / logout ---

def test_login_and_logout(client):
    register(client)
    fresh = TestClient(client.app)
    assert fresh.get("/api/me").status_code == 401
    assert login(fresh).status_code == 200
    assert fresh.get("/api/me").status_code == 200

    r = fresh.post("/api/auth/logout", json={})
    assert r.status_code == 204
    assert fresh.get("/api/me").status_code == 401


def test_logout_invalidates_session_server_side(client):
    register(client)
    token = client.cookies["session"]
    client.post("/api/auth/logout", json={})
    stolen = TestClient(client.app, cookies={"session": token})
    assert stolen.get("/api/me").status_code == 401


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client)
    wrong = login(TestClient(client.app), password="wrong-password")
    unknown = login(TestClient(client.app), email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_is_rate_limited_after_failures(client):
    register(client)
    other = TestClient(client.app)
    for _ in range(5):
        assert login(other, password="wrong-password").status_code == 401
    blocked = login(other)  # even the correct password is refused now
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_expired_session_is_rejected(client, db):
    register(client)
    with db.connection() as conn:
        conn.execute("UPDATE sessions SET expires_at = now() - interval '1 second'")
    assert client.get("/api/me").status_code == 401


def test_forged_cookie_is_rejected(client):
    assert TestClient(client.app, cookies={"session": "garbage"}).get("/api/me").status_code == 401


# --- CSRF ---

def test_form_encoded_login_is_rejected(client):
    register(client)
    r = TestClient(client.app).post(
        "/api/auth/login", data={"email": USER["email"], "password": USER["password"]}
    )
    assert r.status_code == 422


def test_logout_requires_json(client):
    register(client)
    assert client.post("/api/auth/logout").status_code == 415
    assert client.get("/api/me").status_code == 200


# --- profile ---

def test_update_profile_partially(client):
    register(client)
    r = client.patch("/api/me", json={"car": "Toyota Camry 123 ABC 02", "default_commission_pct": 15})
    assert r.status_code == 200
    body = r.json()
    assert body["car"] == "Toyota Camry 123 ABC 02"
    assert body["default_commission_pct"] == 15
    assert body["name"] == "Айдар"  # untouched

    cleared = client.patch("/api/me", json={"default_commission_pct": None}).json()
    assert cleared["default_commission_pct"] is None


@pytest.mark.parametrize("patch, field", [
    ({"default_tz": "+5"}, "default_tz"),
    ({"default_tz": "+15:00"}, "default_tz"),
    ({"default_commission_pct": 120}, "default_commission_pct"),
    ({"name": ""}, "name"),
    ({"name": None}, "name"),
])
def test_update_profile_validation(client, patch, field):
    register(client)
    r = client.patch("/api/me", json=patch)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][-1] == field


def test_profile_cannot_change_email_or_password(client):
    register(client)
    r = client.patch("/api/me", json={"email": "evil@example.com", "password_hash": "x"})
    assert r.status_code == 200
    assert r.json()["email"] == "driver@example.com"


def test_profile_requires_auth(client):
    assert client.get("/api/me").status_code == 401
    assert client.patch("/api/me", json={"car": "x"}).status_code == 401
