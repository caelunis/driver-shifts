"""FastAPI dependencies shared by the driver and admin routes."""

from fastapi import Cookie, Depends, Request, Response, status
from psycopg_pool import ConnectionPool

from app.core.config import get_settings
from app.core.constants import SESSION_COOKIE, SESSION_TTL
from app.core.enums import ErrorCode, Role
from app.core.errors import ApiError
from app.services import accounts


def get_pool(request: Request) -> ConnectionPool:
    return request.app.state.pool


def current_account(
    pool: ConnectionPool = Depends(get_pool), session: str | None = Cookie(default=None)
) -> dict:
    """{"id", "role"} of the logged-in account, or 401."""
    account = accounts.account_by_session(pool, session) if session else None
    if account is None:
        raise ApiError(ErrorCode.NOT_AUTHENTICATED, "Log in first", status=status.HTTP_401_UNAUTHORIZED)
    return account


def require_driver(account: dict = Depends(current_account)) -> int:
    """Driver id. Admins have no diary of their own, so driver endpoints are 403 for them."""
    if account["role"] != Role.DRIVER:
        raise ApiError(ErrorCode.DRIVERS_ONLY, "Only drivers can do this", status=status.HTTP_403_FORBIDDEN)
    return account["id"]


def require_admin(account: dict = Depends(current_account)) -> int:
    if account["role"] != Role.ADMIN:
        raise ApiError(ErrorCode.ADMINS_ONLY, "Only the admin can do this", status=status.HTTP_403_FORBIDDEN)
    return account["id"]


def require_json(request: Request) -> None:
    """CSRF guard for body-less POST requests.

    A cross-site HTML form cannot send Content-Type: application/json, and with
    SameSite=Lax the cookie is not attached to cross-site fetches either.
    Endpoints with a JSON body get this check from FastAPI's body parsing;
    PATCH and DELETE cannot be sent by an HTML form at all.
    """
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise ApiError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "Expected application/json",
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )
