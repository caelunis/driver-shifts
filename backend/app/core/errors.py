"""Domain errors and the single error format of the API.

Every 4xx/5xx response has the body
    {"error": {"code": str, "message": str, "fields": [...], "ctx": {...}}}
`code` is stable and meant for programs (and for localized messages on the client);
`message` is English text for people. `fields` lists per-field problems of a 422:
    {"field": "amount", "code": "greater_than", "message": "...", "ctx": {"gt": 0}}
"""


class ApiError(Exception):
    """An error with an HTTP status and a stable code."""

    status = 400

    def __init__(self, code: str, message: str, *, status: int | None = None,
                 headers: dict | None = None, **ctx):
        super().__init__(message)
        self.code, self.message, self.ctx = code, message, ctx
        self.headers = headers
        if status is not None:
            self.status = status


class NotFound(ApiError):
    status = 404

    def __init__(self, code: str = "not_found", message: str = "Not found", **ctx):
        super().__init__(code, message, **ctx)


class Conflict(ApiError):
    """The request clashes with the current state, e.g. a shift is already open."""

    status = 409


class DomainValidationError(Exception):
    """A business rule rejected a value; reported as a 422 error on that field."""

    def __init__(self, field: str, code: str, message: str, **ctx):
        super().__init__(message)
        self.field, self.code, self.message, self.ctx = field, code, message, ctx

    def as_field(self) -> dict:
        return {"field": self.field, "code": self.code, "message": self.message, "ctx": self.ctx}


class EmailTaken(Exception):
    pass


class PlateTaken(Exception):
    pass


class TripConflict(Exception):
    """A trip with this id already exists, but with different data."""

    def __init__(self, existing):
        self.existing = existing
