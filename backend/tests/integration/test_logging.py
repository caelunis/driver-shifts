"""Request ids, the access log, domain events, and what must never be logged."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.main import create_app
from tests.factories import create_driver

PASSWORD = "horse-battery-9"


@pytest.fixture
def app(db):
    return create_app(db.database)


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.INFO)
    return caplog


def login(client, email="driver@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def records(caplog, message):
    return [r for r in caplog.records if r.getMessage() == message]


def as_json(caplog) -> str:
    """Everything captured, formatted the way production writes it."""
    fmt = JsonFormatter()
    return "\n".join(fmt.format(r) for r in caplog.records)


# --- request ids ---


def test_every_response_has_a_request_id(app):
    r = TestClient(app).get("/api/health")
    assert len(r.headers["x-request-id"]) == 32  # a new uuid4, hex


def test_request_id_from_nginx_is_kept(app):
    r = TestClient(app).get("/api/health", headers={"X-Request-ID": "abc123def456"})
    assert r.headers["x-request-id"] == "abc123def456"


@pytest.mark.parametrize("bad", ["short", "x" * 65, "has spaces in it", "inject\nnewline"])
def test_odd_request_ids_are_replaced(app, bad):
    r = TestClient(app).get("/api/health", headers={"X-Request-ID": bad.replace("\n", "%0A")})
    assert r.headers["x-request-id"] != bad
    assert len(r.headers["x-request-id"]) == 32


# --- access log ---


def test_access_log_line(app, driver_id, logs):
    client = TestClient(app)
    login(client)
    r = client.get(
        "/api/me", headers={"X-Request-ID": "req-0001-abcd", "X-Forwarded-For": "10.0.0.1, 203.0.113.7"}
    )
    [line] = [rec for rec in records(logs, "request") if rec.path == "/api/me"]
    assert (line.method, line.status, line.levelname) == ("GET", 200, "INFO")
    assert line.request_id == "req-0001-abcd" == r.headers["x-request-id"]
    assert line.user_id == driver_id  # who asked
    assert line.client == "203.0.113.7"  # the address nginx appended, not what the client claimed
    assert line.duration_ms >= 0


def test_health_checks_stay_out_of_the_info_log(app, logs):
    logs.set_level(logging.DEBUG, logger="app.access")
    TestClient(app).get("/api/health")
    assert [r.levelno for r in records(logs, "request")] == [logging.DEBUG]


# --- events ---


def test_events_name_the_actor_and_the_object(app, driver_id, logs):
    client = TestClient(app)
    login(client)
    shift = client.post("/api/shifts", json={}).json()
    [started] = records(logs, "shift_started")
    assert (started.driver_id, started.shift_id, started.user_id) == (driver_id, shift["id"], driver_id)
    assert started.request_id is not None


def test_failed_login_is_logged_without_the_password(app, driver_id, logs):
    login(TestClient(app), password="wrong-password-123")
    [failed] = records(logs, "login_failed")
    assert failed.email == "d***@example.com"
    out = as_json(logs)
    assert "wrong-password-123" not in out
    assert "driver@example.com" not in out


def test_secrets_never_reach_the_log(app, db, logs):
    create_driver(db, "admin@example.com", PASSWORD, role="admin")
    admin = TestClient(app)
    login(admin, "admin@example.com")
    admin.post(
        "/api/admin/drivers",
        json={"email": "new@example.com", "password": "brand-new-secret-1", "name": "Новый"},
    )
    new_id = admin.get("/api/admin/drivers").json()[0]["id"]
    admin.patch(f"/api/admin/drivers/{new_id}", json={"password": "another-secret-2"})
    out = as_json(logs)
    for secret in (PASSWORD, "brand-new-secret-1", "another-secret-2", admin.cookies["session"]):
        assert secret not in out
    [updated] = records(logs, "driver_updated")
    assert updated.fields == [] and updated.password_changed is True  # the fact, not the value


# --- unexpected errors ---


def test_unhandled_error_is_logged_with_traceback_and_hidden_from_the_client(db, driver_id, logs):
    app = create_app(db.database)

    @app.get("/api/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    client = TestClient(app)
    login(client)
    r = client.get("/api/boom", headers={"X-Request-ID": "boom-req-0001"})
    assert r.status_code == 500
    body = r.json()["error"]
    assert body["code"] == "internal_error"
    assert body["ctx"] == {"request_id": "boom-req-0001"}
    assert "secret internals" not in r.text
    [err] = records(logs, "unhandled_error")
    assert err.request_id == "boom-req-0001" and err.exc_info is not None
    assert json.loads(JsonFormatter().format(err))["exc"].startswith("Traceback")
    [access] = [rec for rec in records(logs, "request") if rec.path == "/api/boom"]
    assert (access.status, access.levelname) == (500, "ERROR")
