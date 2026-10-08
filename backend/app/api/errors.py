"""Exception handlers that render every error in the format described in app.core.errors."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import orjson
import psycopg
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.constants import DB_RETRY_AFTER
from app.core.enums import ErrorCode
from app.core.errors import ApiError, DomainValidationError
from app.db.errors import is_db_unavailable

log = logging.getLogger(__name__)


def db_unavailable_response() -> "ErrorJSONResponse":
    return error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCode.DB_UNAVAILABLE,
        "The database is unavailable, try again later",
        ctx={"retry_after": DB_RETRY_AFTER},
        headers={"Retry-After": str(DB_RETRY_AFTER)},
    )


class ErrorJSONResponse(JSONResponse):
    """Error bodies are built by hand (no response model), so they are serialized with
    orjson. Regular responses go through FastAPI's own Pydantic serializer, which is
    faster than any response class (FastAPI deprecated ORJSONResponse for that reason)."""

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)


# Where a request value came from; the client only needs the field name itself
_LOCATIONS = {"body", "query", "path", "header", "cookie"}


def error_response(
    status: int,
    code: str,
    message: str,
    *,
    fields: list[dict[str, Any]] | None = None,
    ctx: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> ErrorJSONResponse:
    body = {"code": code, "message": message, "fields": fields or [], "ctx": ctx or {}}
    return ErrorJSONResponse({"error": body}, status_code=status, headers=headers)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)  # Decimal, datetime, exceptions inside pydantic's ctx


def _field(err: Mapping[str, Any]) -> dict[str, Any]:
    loc = [str(p) for p in err["loc"]]
    if loc and loc[0] in _LOCATIONS:
        loc = loc[1:]
    # The rejected input is left out on purpose: it may be a password
    return {
        "field": ".".join(loc) or None,
        "code": err["type"],
        "message": err["msg"],
        "ctx": _json_safe(err.get("ctx", {})),
    }


def validation_response(fields: list[dict[str, Any]]) -> ErrorJSONResponse:
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorCode.VALIDATION_ERROR,
        "Some fields are invalid",
        fields=fields,
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError) -> ErrorJSONResponse:
        return validation_response([_field(e) for e in exc.errors()])

    @app.exception_handler(DomainValidationError)
    async def domain_validation(request: Request, exc: DomainValidationError) -> ErrorJSONResponse:
        return validation_response([_json_safe(exc.as_field())])

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> ErrorJSONResponse:
        return error_response(exc.status, exc.code, exc.message, ctx=_json_safe(exc.ctx), headers=exc.headers)

    async def database_error(request: Request, exc: Exception) -> ErrorJSONResponse:
        if not is_db_unavailable(exc):
            raise exc  # a deadlock or the like: a bug, logged as such with the 500
        log.warning("db_unavailable", extra={"error": type(exc).__name__})
        return db_unavailable_response()

    app.add_exception_handler(psycopg.OperationalError, database_error)
    app.add_exception_handler(PoolTimeout, database_error)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> ErrorJSONResponse:
        # Raised by the framework itself: unknown route, wrong method and the like
        phrase = HTTPStatus(exc.status_code).phrase
        return error_response(
            exc.status_code,
            phrase.lower().replace(" ", "_").replace("-", "_"),
            exc.detail if isinstance(exc.detail, str) else phrase,
            headers=getattr(exc, "headers", None),
        )
