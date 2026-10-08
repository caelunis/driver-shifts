"""Login sessions. Only a hash of each token is stored."""

from datetime import datetime

from app.core.enums import Role
from app.domain.models import Principal
from app.repositories.base import Repository


class SessionRepository(Repository):
    async def insert(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        await self._run(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (token_hash, user_id, expires_at),
        )

    async def find(self, token_hash: str) -> tuple[Principal, bool] | None:
        """The session's account and whether the session is still alive."""
        row = await self._one(
            "SELECT u.id, u.role, s.expires_at > now() AS alive"
            " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = %s",
            (token_hash,),
        )
        return (Principal(row["id"], Role(row["role"])), bool(row["alive"])) if row else None

    async def delete(self, token_hash: str) -> None:
        await self._run("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    async def delete_all_of(self, user_id: int) -> None:
        await self._run("DELETE FROM sessions WHERE user_id = %s", (user_id,))
