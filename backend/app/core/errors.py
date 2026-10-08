"""Domain errors and the single error format of the API.

Every 4xx/5xx response has the body
    {"error": {"code": str, "message": str, "fields": [...], "ctx": {...}}}
`code` is stable and meant for programs (and for localized messages on the client);
`message` is English text for people. `fields` lists per-field problems of a 422:
    {"field": "amount", "code": "greater_than", "message": "...", "ctx": {"gt": 0}}
"""

from typing import TYPE_CHECKING, Any

from fastapi import status as http

from app.core.enums import ErrorCode

if TYPE_CHECKING:
    from app.domain.models import Trip


class ApiError(Exception):
    """An error with an HTTP status and a stable code."""

    status = http.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        headers: dict[str, str] | None = None,
        **ctx: Any,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.ctx = code, message, ctx
        self.headers = headers
        if status is not None:
            self.status = status


class NotFoundError(ApiError):
    status = http.HTTP_404_NOT_FOUND

    def __init__(self, code: str = ErrorCode.NOT_FOUND, message: str = "Not found", **ctx: Any) -> None:
        super().__init__(code, message, **ctx)


class ConflictError(ApiError):
    """The request clashes with the current state, e.g. a shift is already open."""

    status = http.HTTP_409_CONFLICT


class DomainValidationError(Exception):
    """A business rule rejected a value; reported as a 422 error on that field."""

    def __init__(self, field: str, code: str, message: str, **ctx: Any) -> None:
        super().__init__(message)
        self.field, self.code, self.message, self.ctx = field, code, message, ctx

    def as_field(self) -> dict[str, Any]:
        return {"field": self.field, "code": self.code, "message": self.message, "ctx": self.ctx}


class EmailTakenError(Exception):
    pass


class PlateTakenError(Exception):
    pass


class TripConflictError(Exception):
    """A trip with this id already exists, but with different data."""

    def __init__(self, existing: "Trip") -> None:
        super().__init__(existing.id)
        self.existing = existing
