"""Deny by default, roles per router, throttling. The route lists come from the app itself,
so an endpoint added later is checked without anyone extending these tests."""

import re

import pytest
from fastapi.testclient import TestClient

import app.api.guards as guards
from app.core.constants import PUBLIC_ENDPOINTS
from app.main import create_app
from tests.api import code
from tests.factories import create_driver

PASSWORD = "horse-battery-9"
ADMIN_PREFIX = "/api/admin/"
# Endpoints of the driver's own diary; the admin has none
DRIVER_ONLY = re.compile(r"^/api/(shifts|trips|days|summary)(/|$)")


@pytest.fixture
def app(db):
    return create_app(db.database)


def api_routes(app) -> list[tuple[str, str]]:
    """(method, concrete path) of every API endpoint, path parameters filled with 1.
    Taken from the app's OpenAPI schema, which lists every endpoint it serves."""
    found = []
    for template, operations in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", template)
        found += [(m.upper(), path) for m in sorted(operations)]
    return found


def logged_in(app, db, email, role="driver"):
    create_driver(db, email, PASSWORD, role=role)
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return c


def test_every_non_public_endpoint_needs_a_session(app):
    anonymous = TestClient(app)
    checked = 0
    for method, path in api_routes(app):
        if (method, path) in PUBLIC_ENDPOINTS:
            continue
        r = anonymous.request(method, path, json={})
        assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a session"
        assert code(r) == "not_authenticated"
        checked += 1
    assert checked > 20  # the enumeration really found the app's endpoints


def test_an_endpoint_without_any_dependency_is_still_closed(db):
    # What deny-by-default is for: someone adds a handler and forgets the auth dependency
    app = create_app(db.database)

    @app.get("/api/forgotten")
    async def forgotten() -> dict[str, str]:
        return {"secret": "data"}

    r = TestClient(app).get("/api/forgotten")
    assert r.status_code == 401 and "secret" not in r.text


def test_public_endpoints_exist_and_answer_without_a_session(app):
    routes = set(api_routes(app)) | {("GET", "/api/docs"), ("GET", "/api/openapi.json")}
    anonymous = TestClient(app)
    for method, path in PUBLIC_ENDPOINTS:
        if method == "HEAD":
            continue
        assert (method, path) in routes, f"stale entry in PUBLIC_ENDPOINTS: {method} {path}"
        assert anonymous.request(method, path).status_code != 401


def test_admin_cannot_use_driver_endpoints(app, db):
    admin = logged_in(app, db, "admin@example.com", role="admin")
    driver_routes = [(m, p) for m, p in api_routes(app) if DRIVER_ONLY.match(p)]
    assert driver_routes
    for method, path in driver_routes:
        r = admin.request(method, path, json={})
        assert r.status_code == 403, f"{method} {path}: {r.status_code}"
        assert code(r) == "drivers_only"


def test_driver_cannot_use_admin_endpoints(app, db):
    driver = logged_in(app, db, "driver@example.com")
    admin_routes = [
        (m, p) for m, p in api_routes(app) if p.startswith(ADMIN_PREFIX) or p == "/api/admin/drivers"
    ]
    assert admin_routes
    for method, path in admin_routes:
        r = driver.request(method, path, json={})
        assert r.status_code == 403, f"{method} {path}: {r.status_code}"
        assert code(r) == "admins_only"


# --- throttling ---


def test_requests_per_client_are_capped(app, monkeypatch):
    monkeypatch.setattr(guards, "THROTTLE_LIMIT", 3)
    c = TestClient(app)
    first = [c.get("/api/me", headers={"X-Forwarded-For": "203.0.113.5"}) for _ in range(3)]
    assert {r.status_code for r in first} == {401}  # counted, then refused for lack of session
    r = c.get("/api/me", headers={"X-Forwarded-For": "203.0.113.5"})
    assert r.status_code == 429 and code(r) == "too_many_requests"
    assert int(r.headers["Retry-After"]) == r.json()["error"]["ctx"]["retry_after"] > 0
    # Another client is not affected, and health checks are never throttled
    assert c.get("/api/me", headers={"X-Forwarded-For": "203.0.113.6"}).status_code == 401
    assert c.get("/api/health", headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 200


def test_login_attempts_per_client_are_capped(app, monkeypatch):
    monkeypatch.setattr(guards, "LOGIN_ATTEMPTS_PER_CLIENT", 2)
    c = TestClient(app)
    # Different emails each time: the per-email limit never triggers, this one does
    for i in range(2):
        assert (
            c.post("/api/auth/login", json={"email": f"u{i}@example.com", "password": "x"}).status_code == 401
        )
    r = c.post("/api/auth/login", json={"email": "u9@example.com", "password": "x"})
    assert r.status_code == 429 and code(r) == "too_many_attempts"
