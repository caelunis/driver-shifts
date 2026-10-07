"""Exception handlers that render every error in the format described in app.core.errors."""
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import ApiError, DomainValidationError

# Where a request value came from; the client only needs the field name itself
_LOCATIONS = {"body", "query", "path", "header", "cookie"}


def error_response(status: int, code: str, message: str, *, fields: list | None = None,
                   ctx: dict | None = None, headers: dict | None = None) -> JSONResponse:
    body = {"code": code, "message": message, "fields": fields or [], "ctx": ctx or {}}
    return JSONResponse({"error": body}, status_code=status, headers=headers)


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)  # Decimal, datetime, exceptions inside pydantic's ctx


def _field(err: dict) -> dict:
    loc = [str(p) for p in err["loc"]]
    if loc and loc[0] in _LOCATIONS:
        loc = loc[1:]
    # The rejected input is left out on purpose: it may be a password
    return {"field": ".".join(loc) or None, "code": err["type"], "message": err["msg"],
            "ctx": _json_safe(err.get("ctx", {}))}


def validation_response(fields: list[dict]) -> JSONResponse:
    return error_response(422, "validation_error", "Some fields are invalid", fields=fields)


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError):
        return validation_response([_field(e) for e in exc.errors()])

    @app.exception_handler(DomainValidationError)
    async def domain_validation(request: Request, exc: DomainValidationError):
        return validation_response([_json_safe(exc.as_field())])

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, ctx=_json_safe(exc.ctx),
                              headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        # Raised by the framework itself: unknown route, wrong method and the like
        phrase = HTTPStatus(exc.status_code).phrase
        return error_response(exc.status_code, phrase.lower().replace(" ", "_").replace("-", "_"),
                              exc.detail if isinstance(exc.detail, str) else phrase,
                              headers=getattr(exc, "headers", None))
