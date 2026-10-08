"""Driver profiles (`drivers`, 1:1 with a `users` row of role 'driver')."""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

from psycopg.errors import UniqueViolation
from psycopg.rows import DictRow

from app.core.enums import Role
from app.core.errors import PlateTakenError
from app.domain.models import AccountProfile, DriverOverview
from app.repositories.base import Repository

# Profile columns that may be updated; also the whitelist for the dynamic UPDATE below
_UPDATABLE = ("name", "car_model", "car_plate", "default_tz", "default_commission_pct")

_WITH_TOTALS = """
    SELECT u.id, u.email, u.role, u.created_at,
           d.name, d.car_model, d.car_plate, d.default_tz, d.default_commission_pct,
           count(t.id) AS trips_count,
           coalesce(sum(t.amount), 0) AS revenue,
           coalesce(sum(t.amount - t.commission), 0) AS net,
           max(s.local_day) AS last_trip_day
    FROM drivers d
    JOIN users u ON u.id = d.user_id
    LEFT JOIN trips t ON t.driver_id = d.user_id
    LEFT JOIN shifts s ON s.id = t.shift_id
    {filter}
    GROUP BY u.id, d.user_id
    ORDER BY lower(d.name), u.id
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
        user_id: int,
        name: str,
        car_model: str,
        car_plate: str | None,
        default_tz: str,
        default_commission_pct: Decimal | None,
    ) -> None:
        async with self._plate_guard():
            await self._run(
                "INSERT INTO drivers (user_id, name, car_model, car_plate, default_tz,"
                " default_commission_pct) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, name, car_model, car_plate, default_tz, default_commission_pct),
            )

    async def profile(self, user_id: int) -> AccountProfile | None:
        """Any account; driver fields stay None for admins (no profile row)."""
        row = await self._one(
            "SELECT u.id, u.email, u.role, d.name, d.car_model, d.car_plate, d.default_tz,"
            " d.default_commission_pct"
            " FROM users u LEFT JOIN drivers d ON d.user_id = u.id WHERE u.id = %s",
            (user_id,),
        )
        return AccountProfile(**{**row, "role": Role(row["role"])}) if row else None

    async def lock(self, driver_id: int) -> None:
        """Lock the driver's row until the transaction ends.

        Serializes changes to one driver's set of shifts. Without it, concurrent inserts
        checked by the no-overlap EXCLUDE constraint and the one-open-shift index can
        deadlock each other instead of one of them failing cleanly.
        """
        await self._run("SELECT 1 FROM drivers WHERE user_id = %s FOR UPDATE", (driver_id,))

    async def commission_pct(self, driver_id: int) -> Decimal | None:
        row = await self._one("SELECT default_commission_pct FROM drivers WHERE user_id = %s", (driver_id,))
        return row["default_commission_pct"] if row else None

    async def update_profile(self, driver_id: int, changes: Mapping[str, Any]) -> None:
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
            flt = "WHERE d.name ILIKE %s OR u.email ILIKE %s OR d.car_model ILIKE %s OR d.car_plate ILIKE %s"
            q = q.strip()
            params = (_like(q),) * 3 + (_like("".join(q.split()).upper()),)
        return [_overview(r) for r in await self._all(_WITH_TOTALS.format(filter=flt), params)]

    async def with_totals(self, driver_id: int) -> DriverOverview | None:
        row = await self._one(_WITH_TOTALS.format(filter="WHERE d.user_id = %s"), (driver_id,))
        return _overview(row) if row else None
