import logging

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import (
    AccountServiceDep,
    AuthServiceDep,
    LoginLimiterDep,
    SessionCookie,
    require_json,
    set_session_cookie,
)
from app.core.constants import SESSION_COOKIE
from app.core.enums import ErrorCode
from app.core.errors import ApiError
from app.core.logging import mask_email, user_id_var
from app.domain.models import AccountProfile
from app.schemas.accounts import LoginIn, Profile

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)


@router.post("/login", response_model=Profile)
async def login(
    data: LoginIn,
    response: Response,
    auth: AuthServiceDep,
    accounts: AccountServiceDep,
    limiter: LoginLimiterDep,
) -> AccountProfile:
    key = data.email.lower()
    if wait := await limiter.retry_after(key):
        log.warning("login_rate_limited", extra={"email": mask_email(key), "retry_after": wait})
        raise ApiError(
            ErrorCode.TOO_MANY_ATTEMPTS,
            "Too many failed attempts, try again later",
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(wait)},
            retry_after=wait,
        )
    user_id = await auth.authenticate(data.email, data.password)
    if user_id is None:
        await limiter.failure(key)
        log.warning("login_failed", extra={"email": mask_email(key)})
        # Same answer for unknown email and wrong password
        raise ApiError(
            ErrorCode.INVALID_CREDENTIALS, "Invalid email or password", status=status.HTTP_401_UNAUTHORIZED
        )
    await limiter.success(key)
    user_id_var.set(user_id)
    log.info("login_succeeded")
    set_session_cookie(response, await auth.create_session(user_id))
    return await accounts.profile(user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_json)])
async def logout(response: Response, auth: AuthServiceDep, session: SessionCookie = None) -> None:
    if session:
        await auth.end_session(session)
    log.info("logout")
    response.delete_cookie(SESSION_COOKIE, path="/")
