"""FastAPI dependencies shared by the driver and admin routes."""
from fastapi import Cookie, Depends, Request, Response
from psycopg_pool import ConnectionPool

from app.core.config import get_settings
from app.core.errors import ApiError
from app.services import accounts

SESSION_COOKIE = "session"


def get_pool(request: Request) -> ConnectionPool:
    return request.app.state.pool


def current_account(pool: ConnectionPool = Depends(get_pool),
                    session: str | None = Cookie(default=None)) -> dict:
    """{"id", "role"} of the logged-in account, or 401."""
    account = accounts.account_by_session(pool, session) if session else None
    if account is None:
        raise ApiError("not_authenticated", "Log in first", status=401)
    return account


def require_driver(account: dict = Depends(current_account)) -> int:
    """Driver id. Admins have no diary of their own, so driver endpoints are 403 for them."""
    if account["role"] != "driver":
        raise ApiError("drivers_only", "Only drivers can do this", status=403)
    return account["id"]


def require_admin(account: dict = Depends(current_account)) -> int:
    if account["role"] != "admin":
        raise ApiError("admins_only", "Only the admin can do this", status=403)
    return account["id"]


def require_json(request: Request) -> None:
    """CSRF guard for body-less POST requests.

    A cross-site HTML form cannot send Content-Type: application/json, and with
    SameSite=Lax the cookie is not attached to cross-site fetches either.
    Endpoints with a JSON body get this check from FastAPI's body parsing;
    PATCH and DELETE cannot be sent by an HTML form at all.
    """
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise ApiError("unsupported_media_type", "Expected application/json", status=415)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(accounts.SESSION_TTL.total_seconds()),
        httponly=True, samesite="lax", secure=get_settings().cookie_secure, path="/",
    )
