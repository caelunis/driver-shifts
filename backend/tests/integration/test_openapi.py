"""The API docs describe every endpoint: what it does, that it needs a session, how it fails."""

import pytest

from app.core.constants import PUBLIC_ENDPOINTS
from app.main import create_app


@pytest.fixture(scope="module")
def schema():
    return create_app().openapi()


def operations(schema):
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            yield method.upper(), path, op


def test_api_is_versioned(schema):
    assert schema["info"]["version"] == "1.0.0"
    assert all(path.startswith("/api/v1/") or path == "/api/health" for path in schema["paths"])


def test_every_endpoint_has_a_summary(schema):
    missing = [f"{m} {p}" for m, p, op in operations(schema) if not op.get("summary")]
    assert missing == []


def test_protected_endpoints_declare_the_session_cookie(schema):
    assert schema["components"]["securitySchemes"]["session"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "session",
        "description": "Set by POST /api/v1/auth/login; HttpOnly, so a browser sends it by itself",
    }
    for method, path, op in operations(schema):
        protected = (method, path) not in PUBLIC_ENDPOINTS
        assert (op.get("security") == [{"session": []}]) == protected, f"{method} {path}"


def test_errors_are_documented_with_the_error_body(schema):
    for method, path, op in operations(schema):
        for status, response in op["responses"].items():
            if status.startswith(("4", "5")):
                ref = response["content"]["application/json"]["schema"]["$ref"]
                assert ref.endswith("/ErrorBody"), f"{method} {path} {status}: {ref}"
    assert "HTTPValidationError" not in schema["components"]["schemas"]  # FastAPI's default 422


def test_every_reference_resolves(schema):
    """Broken $refs make client generators (openapi-typescript) fail."""
    components = schema["components"]["schemas"]

    def refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                yield node["$ref"]
            for value in node.values():
                yield from refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from refs(value)

    for ref in refs(schema):
        assert ref.startswith("#/components/schemas/"), ref
        assert ref.rsplit("/", 1)[1] in components, f"unresolved {ref}"
