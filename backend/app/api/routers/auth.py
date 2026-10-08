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
from app.domain.models import AccountProfile
from app.schemas.accounts import LoginIn, Profile

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Profile)
async def login(
    data: LoginIn,
    response: Response,
    auth: AuthServiceDep,
    accounts: AccountServiceDep,
    limiter: LoginLimiterDep,
) -> AccountProfile:
    key = data.email.lower()
    if wait := limiter.retry_after(key):
        raise ApiError(
            ErrorCode.TOO_MANY_ATTEMPTS,
            "Too many failed attempts, try again later",
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(wait)},
            retry_after=wait,
        )
    user_id = await auth.authenticate(data.email, data.password)
    if user_id is None:
        limiter.failure(key)
        # Same answer for unknown email and wrong password
        raise ApiError(
            ErrorCode.INVALID_CREDENTIALS, "Invalid email or password", status=status.HTTP_401_UNAUTHORIZED
        )
    limiter.success(key)
    set_session_cookie(response, await auth.create_session(user_id))
    return await accounts.profile(user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_json)])
async def logout(response: Response, auth: AuthServiceDep, session: SessionCookie = None) -> None:
    if session:
        await auth.end_session(session)
    response.delete_cookie(SESSION_COOKIE, path="/")
