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


def tid(name: str) -> str:
    """A stable trip id for a readable name: tid("t1") is the same UUID in every test."""
    from uuid import NAMESPACE_URL, uuid5

    return str(uuid5(NAMESPACE_URL, f"trip/{name}"))


def sid(n: int) -> str:
    """The id of the n-th shift created in a test (see the `shift_ids` fixture)."""
    return f"00000000-0000-7000-8000-{n:012d}"
