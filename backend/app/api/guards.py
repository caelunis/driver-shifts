"""Access control and throttling, applied to every request before routing.

Deny by default: a path under /api is served without a session only if it is listed in
PUBLIC_ENDPOINTS. A new endpoint is protected without anyone remembering to add a
dependency; the roles are then checked once per router (app/api/routers/*).
"""

import logging

from fastapi import status as http
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import db_unavailable_response, error_response
from app.api.middleware import client_address
from app.core.constants import (
    API_PREFIX,
    API_V1,
    LOGIN_ATTEMPTS_PER_CLIENT,
    LOGIN_ATTEMPTS_WINDOW,
    PUBLIC_ENDPOINTS,
    SESSION_COOKIE,
    THROTTLE_LIMIT,
    THROTTLE_WINDOW,
)
from app.core.enums import ErrorCode
from app.core.logging import user_id_var
from app.core.ratelimit import RateLimitStore
from app.db.errors import is_db_unavailable
from app.services.auth import AuthService

log = logging.getLogger(__name__)

# Health checks are polled by Docker and never throttled
_UNTHROTTLED = frozenset({"/api/health"})


def is_public(method: str, path: str) -> bool:
    return (method, path.rstrip("/") or "/") in PUBLIC_ENDPOINTS


class AuthMiddleware:
    """Resolves the session cookie into the request's principal (request.state.principal),
    or answers 401 for any non-public API path. Dependencies read the principal from the
    request state instead of looking the session up again."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(API_PREFIX):
            await self.app(scope, receive, send)
            return
        token = HTTPConnection(scope).cookies.get(SESSION_COOKIE)
        principal = None
        if token:
            state = scope["app"].state
            try:
                principal = await AuthService(state.db, state.cache).principal(token)
            except Exception as e:
                if not is_db_unavailable(e):
                    raise
                # Neither the database nor the cache knows this session right now
                await db_unavailable_response()(scope, receive, send)
                return
        if principal is not None:
            scope.setdefault("state", {})["principal"] = principal
            user_id_var.set(principal.id)  # every log record of this request names the account
        elif not is_public(scope["method"], scope["path"]):
            response = error_response(http.HTTP_401_UNAUTHORIZED, ErrorCode.NOT_AUTHENTICATED, "Log in first")
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class ThrottleMiddleware:
    """Caps the request rate per client address, and login attempts per address more
    tightly. Answers 429 with Retry-After in the usual error format."""

    def __init__(self, app: ASGIApp, store: RateLimitStore) -> None:
        self.app = app
        self.store = store

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith(API_PREFIX) or path in _UNTHROTTLED:
            await self.app(scope, receive, send)
            return
        client = client_address(scope) or "unknown"
        state = await self.store.hit(f"requests:{client}", THROTTLE_WINDOW)
        limit, code = THROTTLE_LIMIT, ErrorCode.TOO_MANY_REQUESTS
        if state.count <= limit and scope["method"] == "POST" and path == f"{API_V1}/auth/login":
            state = await self.store.hit(f"logins:{client}", LOGIN_ATTEMPTS_WINDOW)
            limit, code = LOGIN_ATTEMPTS_PER_CLIENT, ErrorCode.TOO_MANY_ATTEMPTS
        if state.count > limit:
            log.warning("throttled", extra={"client": client, "path": path, "retry_after": state.retry_after})
            response = error_response(
                http.HTTP_429_TOO_MANY_REQUESTS,
                code,
                "Too many requests, try again later",
                ctx={"retry_after": state.retry_after},
                headers={"Retry-After": str(state.retry_after)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
