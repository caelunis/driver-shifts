"""Accounts (`users`): email, password hash and role."""

from uuid import UUID

from psycopg.errors import UniqueViolation

from app.core.enums import Role
from app.core.errors import EmailTakenError
from app.core.ids import uuid7
from app.domain.models import Credentials
from app.repositories.base import Repository


class UserRepository(Repository):
    async def insert(self, email: str, password_hash: str, role: Role) -> UUID:
        user_id = uuid7()
        try:
            # A savepoint, so a duplicate does not abort the caller's whole transaction
            async with self._conn.transaction():
                await self._run(
                    "INSERT INTO users (id, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                    (user_id, email.lower(), password_hash, role),
                )
        except UniqueViolation as e:
            raise EmailTakenError(email) from e
        return user_id

    async def credentials(self, email: str) -> Credentials | None:
        row = await self._one(
            "SELECT id, role, password_hash FROM users WHERE lower(email) = lower(%s)", (email,)
        )
        return Credentials(row["id"], Role(row["role"]), row["password_hash"]) if row else None

    async def email_of(self, user_id: UUID) -> str | None:
        row = await self._one("SELECT email FROM users WHERE id = %s", (user_id,))
        return str(row["email"]) if row else None

    async def any_exist(self) -> bool:
        return await self._one("SELECT 1 FROM users LIMIT 1") is not None

    async def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        await self._run("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))

    async def delete_driver(self, user_id: UUID) -> bool:
        """Delete a driver account (never an admin). The profile, shifts, trips and
        sessions go with it via ON DELETE CASCADE."""
        return await self._run("DELETE FROM users WHERE id = %s AND role = %s", (user_id, Role.DRIVER)) > 0
