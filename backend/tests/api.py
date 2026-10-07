"""Readers for the API's error format: {"error": {"code", "message", "fields", "ctx"}}."""


def code(r) -> str:
    """The error code of a response."""
    return r.json()["error"]["code"]


def fields(r) -> dict[str, str]:
    """{field: code} of every field error of a 422."""
    return {f["field"]: f["code"] for f in r.json()["error"]["fields"]}


def error(r) -> tuple[str, str]:
    """(field, code) of a 422 with exactly one field error."""
    [f] = r.json()["error"]["fields"]
    return f["field"], f["code"]


def field_ctx(r) -> dict:
    """ctx of the single field error."""
    [f] = r.json()["error"]["fields"]
    return f["ctx"]
