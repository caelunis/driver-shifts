from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from psycopg_pool import ConnectionPool

from app.api.deps import SESSION_COOKIE, get_pool, require_json, set_session_cookie
from app.core.security import LoginLimiter
from app.schemas.accounts import LoginIn, Profile
from app.services import accounts

router = APIRouter(prefix="/api/auth")


@router.post("/login", response_model=Profile)
def login(data: LoginIn, request: Request, response: Response,
          pool: ConnectionPool = Depends(get_pool)):
    limiter: LoginLimiter = request.app.state.login_limiter
    key = data.email.lower()
    if wait := limiter.retry_after(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts",
                            headers={"Retry-After": str(wait)})
    user_id = accounts.authenticate(pool, data.email, data.password)
    if user_id is None:
        limiter.failure(key)
        # Same answer for unknown email and wrong password
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    limiter.success(key)
    set_session_cookie(response, accounts.create_session(pool, user_id))
    return accounts.get_profile(pool, user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_json)])
def logout(response: Response, session: str | None = Cookie(default=None),
           pool: ConnectionPool = Depends(get_pool)):
    if session:
        accounts.end_session(pool, session)
    response.delete_cookie(SESSION_COOKIE, path="/")
