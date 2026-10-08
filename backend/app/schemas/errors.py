"""The error body, described for the API docs. The handlers in app/api/errors.py build it."""

from typing import Any

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    field: str | None = Field(description="The request field, e.g. ended_at; null for the body as a whole")
    code: str = Field(description="Stable, e.g. end_before_start; clients translate it")
    message: str = Field(description="English, a fallback for unknown codes")
    ctx: dict[str, Any] = Field(description="Values for the message, e.g. {'expected': 360}")


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable code: validation_error, shift_locked, trip_overlap, …")
    message: str
    fields: list[FieldError] = Field(description="Every invalid field of a 422, all at once")
    ctx: dict[str, Any]


class ErrorBody(BaseModel):
    """Every 4xx and 5xx response. The rejected input itself is never echoed."""

    error: ErrorDetail

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Some fields are invalid",
                        "fields": [
                            {"field": "fare", "code": "greater_than", "message": "…", "ctx": {"gt": 0}}
                        ],
                        "ctx": {},
                    }
                }
            ]
        }
    }


def responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` for a route or router: the listed statuses with the error body."""
    text = {
        401: "No session, or it expired",
        403: "The account's role may not do this",
        404: "Not found",
        409: "Clashes with the current state (see error.code)",
        415: "Expected application/json",
        422: "Invalid fields: error.fields lists all of them",
        429: "Too many requests; see the Retry-After header",
    }
    return {s: {"model": ErrorBody, "description": text.get(s, "Error")} for s in statuses}
