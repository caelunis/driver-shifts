"""Login and sessions."""

import asyncio
import hashlib
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import orjson

from app.cache.store import Cache
from app.core.constants import SESSION_CACHE_TTL, SESSION_TOKEN_BYTES, SESSION_TTL
from app.core.enums import Role
from app.core.security import hash_password, verify_password
from app.db.database import Database
from app.db.errors import is_db_unavailable
from app.domain.models import Principal

log = logging.getLogger(__name__)

# Verified against when the email is unknown, so a login attempt takes the same
# time whether or not the account exists (no account enumeration via timing).
_DUMMY_HASH = hash_password(secrets.token_hex(SESSION_TOKEN_BYTES))


def _token_hash(token: str) -> str:
    # Only a hash of the session token is stored: a leaked sessions table
    # cannot be used to log in.
    return hashlib.sha256(token.encode()).hexdigest()


def session_version(user_id: UUID) -> str:
    """Bumped when all of an account's sessions end (new password, deleted driver)."""
    return f"ver:sessions:{user_id}"


class AuthService:
    """Sessions are resolved through the cache: the database is asked again once a minute
    per session, and while it is down a known session keeps working until it expires."""

    def __init__(self, db: Database, cache: Cache) -> None:
        self._db = db
        self._cache = cache

    async def authenticate(self, email: str, password: str) -> UUID | None:
        """The account id if the password is right."""
        async with self._db.unit_of_work() as uow:
            creds = await uow.users.credentials(email)
        # scrypt is deliberately slow CPU work: off the event loop, so other requests go on
        stored = creds.password_hash if creds else _DUMMY_HASH
        ok = await asyncio.to_thread(verify_password, password, stored)
        return creds.id if creds and ok else None

    async def create_session(self, user_id: UUID) -> str:
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        async with self._db.unit_of_work() as uow:
            await uow.sessions.insert(_token_hash(token), user_id, datetime.now(UTC) + SESSION_TTL)
        return token

    async def principal(self, token: str) -> Principal | None:
        """The account behind a live session; None for unknown or expired tokens.

        Raises the database's error if it is down and the session is not in the cache.
        """
        key = f"session:{_token_hash(token)}"
        raw = await self._cache.get(key)
        cached: dict[str, str] | None = orjson.loads(raw) if raw else None
        now = time.time()
        if cached and float(cached["expires"]) > now:
            principal = Principal(UUID(cached["id"]), Role(cached["role"]))
            # Still valid only if nobody ended all of the account's sessions meanwhile
            still_valid = cached["sessions"] == await self._cache.namespace(session_version(principal.id))
            if still_valid and now - float(cached["at"]) < SESSION_CACHE_TTL.total_seconds():
                return principal
        else:
            still_valid = False

        try:
            async with self._db.unit_of_work() as uow:
                found = await uow.sessions.find(_token_hash(token))
                if found is not None and found[1] <= datetime.now(UTC):
                    await uow.sessions.delete(_token_hash(token))
                    log.info("session_expired", extra={"account_id": found[0].id})
                    found = None
        except Exception as e:
            if cached and still_valid and is_db_unavailable(e):
                # The database is down: trust the copy until the session would expire
                return Principal(UUID(cached["id"]), Role(cached["role"]))
            raise
        if found is None:
            await self._cache.delete(key)
            return None
        principal, expires = found
        entry = {
            "id": str(principal.id),
            "role": principal.role,
            "expires": str(expires.timestamp()),
            "at": str(now),
            "sessions": await self._cache.namespace(session_version(principal.id)),
        }
        ttl = max(expires - datetime.now(UTC), timedelta(seconds=1))
        await self._cache.set(key, orjson.dumps(entry), ttl)
        return principal

    async def end_session(self, token: str) -> None:
        async with self._db.unit_of_work() as uow:
            await uow.sessions.delete(_token_hash(token))
        await self._cache.delete(f"session:{_token_hash(token)}")
