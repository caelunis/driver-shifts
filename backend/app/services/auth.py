"""Login and sessions."""

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime

from app.core.constants import SESSION_TOKEN_BYTES, SESSION_TTL
from app.core.security import hash_password, verify_password
from app.db.database import Database
from app.domain.models import Principal

# Verified against when the email is unknown, so a login attempt takes the same
# time whether or not the account exists (no account enumeration via timing).
_DUMMY_HASH = hash_password(secrets.token_hex(SESSION_TOKEN_BYTES))


def _token_hash(token: str) -> str:
    # Only a hash of the session token is stored: a leaked sessions table
    # cannot be used to log in.
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def authenticate(self, email: str, password: str) -> int | None:
        """The account id if the password is right."""
        async with self._db.unit_of_work() as uow:
            creds = await uow.users.credentials(email)
        # scrypt is deliberately slow CPU work: off the event loop, so other requests go on
        stored = creds.password_hash if creds else _DUMMY_HASH
        ok = await asyncio.to_thread(verify_password, password, stored)
        return creds.id if creds and ok else None

    async def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        async with self._db.unit_of_work() as uow:
            await uow.sessions.insert(_token_hash(token), user_id, datetime.now(UTC) + SESSION_TTL)
        return token

    async def principal(self, token: str) -> Principal | None:
        """The account behind a live session; None for unknown or expired tokens."""
        async with self._db.unit_of_work() as uow:
            found = await uow.sessions.find(_token_hash(token))
            if found is None:
                return None
            principal, alive = found
            if not alive:
                await uow.sessions.delete(_token_hash(token))
                return None
            return principal

    async def end_session(self, token: str) -> None:
        async with self._db.unit_of_work() as uow:
            await uow.sessions.delete(_token_hash(token))
