"""Request context and the access log."""

import logging
import re
import time
import uuid
from typing import Any

from fastapi import status as http
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.core.enums import ErrorCode
from app.core.logging import request_id_var, user_id_var

log = logging.getLogger("app.access")

REQUEST_ID_HEADER = "x-request-id"
# An id from the client or nginx is kept only if it looks like one: it ends up in logs
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
# Polled every few seconds by Docker: logged only at DEBUG
_QUIET_PATHS = frozenset({"/api/health"})


def client_address(scope: Scope) -> str | None:
    """The client's address. Behind nginx the connection comes from nginx itself; nginx
    appends the real address to X-Forwarded-For, so the last entry is the trustworthy one
    (earlier entries are whatever the client sent)."""
    headers: dict[bytes, bytes] = dict(scope["headers"])
    forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1")
    if forwarded:
        return forwarded.rsplit(",", 1)[-1].strip()
    client = scope.get("client")
    return str(client[0]) if client else None


class RequestContextMiddleware:
    """Gives every request an id (from X-Request-ID, set by nginx, or a new one), makes it
    part of every log record of the request, returns it in the response headers and
    writes one access log line per request.

    It also turns an unhandled exception into the usual error body (500, internal_error)
    and logs it with its traceback, while the request id is still known: Starlette's own
    handler for Exception runs outside every middleware, after this context is gone.

    A plain ASGI middleware rather than BaseHTTPMiddleware: it runs in the request's own
    task, so the context variables it sets are those the handlers see.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming = headers.get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        rid_token = request_id_var.set(request_id)
        uid_token = user_id_var.set(None)
        started = time.perf_counter()
        status = http.HTTP_500_INTERNAL_SERVER_ERROR  # if the app fails before sending a response
        started_response = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, started_response
            if message["type"] == "http.response.start":
                status, started_response = message["status"], True
                message["headers"] = [*message.get("headers", []), (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            # A bug or an outage: details go to the log, never to the client; the request id
            # in the response lets support find this entry
            log.exception("unhandled_error", extra={"error": type(exc).__name__})
            if started_response:
                raise  # too late for an error body; the server closes the connection
            response = error_response(
                http.HTTP_500_INTERNAL_SERVER_ERROR,
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                ctx={"request_id": request_id},
            )
            await response(scope, receive, send_with_id)
        finally:
            path = scope["path"]
            fields: dict[str, Any] = {
                "method": scope["method"],
                "path": path,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            if client := client_address(scope):
                fields["client"] = client
            server_error = status >= http.HTTP_500_INTERNAL_SERVER_ERROR
            if server_error:
                level = logging.ERROR
            elif path in _QUIET_PATHS:
                level = logging.DEBUG
            else:
                level = logging.INFO
            log.log(level, "request", extra=fields)
            user_id_var.reset(uid_token)
            request_id_var.reset(rid_token)
