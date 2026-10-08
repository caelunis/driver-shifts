"""A cache of API reads in front of the database, and what keeps it correct.

Reads (GET) are cached per account: the key holds the account, the path and the query,
so nobody is ever served someone else's response. Freshness is not left to a TTL alone:
every driver's data has a version counter, part of the key, and any successful write
bumps the versions it touches before its response goes out. A read after a write never
sees the old copy.

When the database is down, a read whose fresh copy has expired gets the last copy
anyway, marked with `X-Data-Stale: true`; without any copy it is a 503.
"""

import logging
import re
import time
from typing import Any

import orjson
from fastapi import status as http
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.cache.store import Cache
from app.core.constants import API_V1, CACHE_FRESH_TTL, CACHE_STALE_TTL
from app.domain.models import Principal

log = logging.getLogger(__name__)

# Paths that are never cached: the docs, and the session endpoints
_UNCACHED = (f"{API_V1}/docs", f"{API_V1}/openapi.json", f"{API_V1}/auth/")
_ADMIN = f"{API_V1}/admin/"
_ADMIN_DRIVER = re.compile(rf"^{API_V1}/admin/drivers/([0-9a-fA-F-]{{36}})(/|$)")
DRIVERS_LIST_VERSION = "ver:drivers"


def user_version(user_id: object) -> str:
    return f"ver:user:{user_id}"


def versions_for(principal: Principal, path: str) -> list[str]:
    """The version counters a path depends on: the driver whose data it shows (the caller,
    or the one in an admin path), and for admin paths the list of drivers with totals."""
    keys = []
    if match := _ADMIN_DRIVER.match(path):
        keys.append(user_version(match.group(1).lower()))
    elif not path.startswith(_ADMIN):
        keys.append(user_version(principal.id))
    if path.startswith(f"{API_V1}/admin/drivers"):
        keys.append(DRIVERS_LIST_VERSION)
    return keys


def _versions_changed_by_write(principal: Principal, path: str) -> list[str]:
    # A trip or shift changes its driver's diary and the admin's totals alike
    return [*versions_for(principal, path), DRIVERS_LIST_VERSION]


class ResponseCacheMiddleware:
    def __init__(self, app: ASGIApp, cache: Cache) -> None:
        self.app = app
        self.cache = cache

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        principal: Principal | None = scope.get("state", {}).get("principal")
        if (
            scope["type"] != "http"
            or principal is None  # public endpoints: nothing per-account to cache
            or not path.startswith(f"{API_V1}/")
            or path.startswith(_UNCACHED)
        ):
            await self.app(scope, receive, send)
            return
        if scope["method"] == "GET":
            await self._read(scope, receive, send, principal, path)
        else:
            await self._write(scope, receive, send, principal, path)

    async def _write(
        self, scope: Scope, receive: Receive, send: Send, principal: Principal, path: str
    ) -> None:
        async def bump_then_send(message: Message) -> None:
            if message["type"] == "http.response.start" and 200 <= message["status"] < 300:  # noqa: PLR2004
                # Before the client hears "done": its next read must not find the old copy
                await self.cache.bump(*_versions_changed_by_write(principal, path))
            await send(message)

        await self.app(scope, receive, bump_then_send)

    async def _read(
        self, scope: Scope, receive: Receive, send: Send, principal: Principal, path: str
    ) -> None:
        namespace = await self.cache.namespace(*versions_for(principal, path))
        query = scope.get("query_string", b"").decode("latin-1")
        key = f"resp:{namespace}:{principal.id}:{path}?{query}"

        raw = await self.cache.get(key)
        cached: dict[str, Any] | None = orjson.loads(raw) if raw else None
        if cached and time.time() - cached["at"] < CACHE_FRESH_TTL.total_seconds():
            await _replay(send, cached, {"x-cache": "hit"})
            return

        start: Message = {}
        body = bytearray()

        async def capture(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
            elif message["type"] == "http.response.body":
                body.extend(message.get("body", b""))

        await self.app(scope, receive, capture)
        status = start.get("status", http.HTTP_500_INTERNAL_SERVER_ERROR)

        if status == http.HTTP_200_OK:
            entry = {"at": time.time(), "status": status, "body": body.decode()}
            await self.cache.set(key, orjson.dumps(entry), CACHE_STALE_TTL)
            await _replay(send, entry, {"x-cache": "miss"})
        elif status == http.HTTP_503_SERVICE_UNAVAILABLE and cached:
            # The database is down: the last copy beats no answer, flagged as possibly old
            log.warning("served_stale", extra={"path": path, "age_s": round(time.time() - cached["at"])})
            await _replay(send, cached, {"x-cache": "stale", "x-data-stale": "true"})
        else:
            await send(start)
            await send({"type": "http.response.body", "body": bytes(body)})


async def _replay(send: Send, entry: dict[str, Any], extra_headers: dict[str, str]) -> None:
    body = entry["body"].encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        *[(k.encode(), v.encode()) for k, v in extra_headers.items()],
    ]
    await send({"type": "http.response.start", "status": entry["status"], "headers": headers})
    await send({"type": "http.response.body", "body": body})
