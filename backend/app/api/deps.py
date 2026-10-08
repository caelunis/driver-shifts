"""FastAPI dependencies: the database, the services built on it, and who is asking.

Routers declare what they need with the Annotated aliases below, e.g.
`async def handler(trips: TripServiceDep, driver_id: DriverId)`.
"""

from typing import Annotated

from fastapi import Cookie, Depends, Request, Response, status

from app.core.config import get_settings
from app.core.constants import SESSION_COOKIE, SESSION_TTL
from app.core.enums import ErrorCode, Role
from app.core.errors import ApiError
from app.core.ratelimit import LoginLimiter
from app.db.database import Database
from app.domain.models import Principal
from app.services.accounts import AccountService
from app.services.auth import AuthService
from app.services.shifts import ShiftService
from app.services.trips import TripService


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_login_limiter(request: Request) -> LoginLimiter:
    limiter: LoginLimiter = request.app.state.login_limiter
    return limiter


DbDep = Annotated[Database, Depends(get_db)]
LoginLimiterDep = Annotated[LoginLimiter, Depends(get_login_limiter)]


# --- services: built per request on the shared pool; they hold no state of their own ---


def get_auth_service(db: DbDep) -> AuthService:
    return AuthService(db)


def get_account_service(db: DbDep) -> AccountService:
    return AccountService(db)


def get_shift_service(db: DbDep) -> ShiftService:
    return ShiftService(db)


def get_trip_service(db: DbDep) -> TripService:
    return TripService(db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
ShiftServiceDep = Annotated[ShiftService, Depends(get_shift_service)]
TripServiceDep = Annotated[TripService, Depends(get_trip_service)]
SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


# --- who is asking ---


def current_principal(request: Request) -> Principal:
    """The logged-in account, as resolved by AuthMiddleware (app/api/guards.py).

    Non-public paths never get here without one; the check stays as a second line of
    defence, e.g. for a path wrongly listed as public.
    """
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        raise ApiError(ErrorCode.NOT_AUTHENTICATED, "Log in first", status=status.HTTP_401_UNAUTHORIZED)
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_driver(principal: CurrentPrincipal) -> int:
    """Driver id. Admins have no diary of their own, so driver endpoints are 403 for them."""
    if principal.role != Role.DRIVER:
        raise ApiError(ErrorCode.DRIVERS_ONLY, "Only drivers can do this", status=status.HTTP_403_FORBIDDEN)
    return principal.id


def require_admin(principal: CurrentPrincipal) -> int:
    if principal.role != Role.ADMIN:
        raise ApiError(ErrorCode.ADMINS_ONLY, "Only the admin can do this", status=status.HTTP_403_FORBIDDEN)
    return principal.id


DriverId = Annotated[int, Depends(require_driver)]
AdminId = Annotated[int, Depends(require_admin)]


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
