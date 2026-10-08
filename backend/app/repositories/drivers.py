"""Driver profiles (`drivers`, 1:1 with a `users` row of role 'driver')."""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.rows import DictRow

from app.core.enums import Role
from app.core.errors import PlateTakenError
from app.domain.models import AccountProfile, DriverOverview
from app.repositories.base import Repository

# Profile columns that may be updated; also the whitelist for the dynamic UPDATE below
_UPDATABLE = ("full_name", "car_model", "car_plate", "timezone", "commission_percent")

_WITH_TOTALS = """
    SELECT u.id, u.email, u.role, u.created_at,
           d.full_name, d.car_model, d.car_plate, d.timezone, d.commission_percent,
           count(t.id) AS trips_count,
           coalesce(sum(t.fare), 0) AS revenue,
           coalesce(sum(t.fare - t.commission_amount), 0) AS net_income,
           max(s.work_date) AS last_work_date
    FROM drivers d
    JOIN users u ON u.id = d.user_id
    LEFT JOIN trips t ON t.driver_id = d.user_id
    LEFT JOIN shifts s ON s.id = t.shift_id
    {filter}
    GROUP BY u.id, d.user_id
    ORDER BY lower(d.full_name), u.id
"""


def _like(q: str) -> str:
    """Substring pattern for ILIKE with the user's % and _ taken literally."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _overview(row: DictRow) -> DriverOverview:
    return DriverOverview(**{**row, "role": Role(row["role"])})


class DriverRepository(Repository):
    @asynccontextmanager
    async def _plate_guard(self) -> AsyncIterator[None]:
        """A savepoint that turns a duplicate plate into PlateTakenError."""
        try:
            async with self._conn.transaction():
                yield
        except UniqueViolation as e:
            if e.diag.constraint_name == "drivers_car_plate_key":
                raise PlateTakenError() from e
            raise

    async def insert_profile(
        self,
        user_id: UUID,
        full_name: str,
        car_model: str,
        car_plate: str | None,
        timezone: str,
        commission_percent: Decimal | None,
    ) -> None:
        async with self._plate_guard():
            await self._run(
                "INSERT INTO drivers (user_id, full_name, car_model, car_plate, timezone,"
                " commission_percent) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, full_name, car_model, car_plate, timezone, commission_percent),
            )

    async def profile(self, user_id: UUID) -> AccountProfile | None:
        """Any account; driver fields stay None for admins (no profile row)."""
        row = await self._one(
            "SELECT u.id, u.email, u.role, d.full_name, d.car_model, d.car_plate, d.timezone,"
            " d.commission_percent"
            " FROM users u LEFT JOIN drivers d ON d.user_id = u.id WHERE u.id = %s",
            (user_id,),
        )
        return AccountProfile(**{**row, "role": Role(row["role"])}) if row else None

    async def lock(self, driver_id: UUID) -> None:
        """Lock the driver's row until the transaction ends.

        Serializes changes to one driver's set of shifts. Without it, concurrent inserts
        checked by the no-overlap EXCLUDE constraint and the one-open-shift index can
        deadlock each other instead of one of them failing cleanly.
        """
        await self._run("SELECT 1 FROM drivers WHERE user_id = %s FOR UPDATE", (driver_id,))

    async def commission_percent(self, driver_id: UUID) -> Decimal | None:
        row = await self._one("SELECT commission_percent FROM drivers WHERE user_id = %s", (driver_id,))
        return row["commission_percent"] if row else None

    async def update_profile(self, driver_id: UUID, changes: Mapping[str, Any]) -> None:
        columns = {k: v for k, v in changes.items() if k in _UPDATABLE}
        if not columns:
            return
        assignments = ", ".join(f"{k} = %s" for k in columns)
        async with self._plate_guard():
            await self._run(
                f"UPDATE drivers SET {assignments} WHERE user_id = %s", (*columns.values(), driver_id)
            )

    async def list_with_totals(self, q: str | None = None) -> list[DriverOverview]:
        """Drivers only: admins have no profile row, so the inner join leaves them out."""
        params: tuple[str, ...] = ()
        flt = ""
        if q and q.strip():
            # Plates are stored without spaces, so "123 ABC" finds "123ABC02"
            flt = (
                "WHERE d.full_name ILIKE %s OR u.email ILIKE %s OR d.car_model ILIKE %s"
                " OR d.car_plate ILIKE %s"
            )
            q = q.strip()
            params = (_like(q),) * 3 + (_like("".join(q.split()).upper()),)
        return [_overview(r) for r in await self._all(_WITH_TOTALS.format(filter=flt), params)]

    async def with_totals(self, driver_id: UUID) -> DriverOverview | None:
        row = await self._one(_WITH_TOTALS.format(filter="WHERE d.user_id = %s"), (driver_id,))
        return _overview(row) if row else None
