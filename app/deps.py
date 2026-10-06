"""FastAPI dependencies shared by the driver and admin routes."""
import os

from fastapi import Cookie, Depends, HTTPException, Request, Response, status

from . import accounts
from .storage import TripStorage

SESSION_COOKIE = "session"
# Set COOKIE_SECURE=1 behind HTTPS; plain-HTTP localhost needs it off
COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"


def get_storage(request: Request) -> TripStorage:
    return request.app.state.storage


def current_account(storage: TripStorage = Depends(get_storage),
                    session: str | None = Cookie(default=None)) -> dict:
    """{"id", "role"} of the logged-in account, or 401."""
    account = accounts.account_by_session(storage.pool, session) if session else None
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return account


def require_driver(account: dict = Depends(current_account)) -> int:
    """Driver id. Admins have no diary of their own, so driver endpoints are 403 for them."""
    if account["role"] != "driver":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Drivers only")
    return account["id"]


def require_admin(account: dict = Depends(current_account)) -> int:
    if account["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return account["id"]


def require_json(request: Request) -> None:
    """CSRF guard for body-less POST requests.

    A cross-site HTML form cannot send Content-Type: application/json, and with
    SameSite=Lax the cookie is not attached to cross-site fetches either.
    Endpoints with a JSON body get this check from FastAPI's body parsing;
    PATCH and DELETE cannot be sent by an HTML form at all.
    """
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Expected application/json")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(accounts.SESSION_TTL.total_seconds()),
        httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/",
    )
