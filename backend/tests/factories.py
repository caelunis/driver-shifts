"""Test helpers that create data through the same services the app uses."""

from datetime import datetime
from uuid import UUID

from app.core.enums import Role
from app.core.security import hash_password
from app.db.database import Database
from app.schemas.accounts import DriverCreate
from app.services.accounts import AccountService
from app.services.shifts import ShiftService
from tests.conftest import TestDb


def create_driver(
    db: TestDb, email: str, password: str, name: str = "Водитель", role: str = "driver", **profile: object
) -> str:
    """A driver with a profile, or (role="admin") a bare account."""
    if role == Role.DRIVER:
        data = DriverCreate(email=email, password=password, full_name=name, **profile)  # type: ignore[arg-type]
        return str(db.service(AccountService).create_driver(data).id)

    async def insert(database: Database) -> UUID:
        async with database.unit_of_work() as uow:
            # The role goes in as given, unchecked: tests also probe the database's own CHECK
            return await uow.users.insert(email, hash_password(password), role)  # type: ignore[arg-type]

    return str(db.run(insert, db.database))


def set_commission_pct(db: TestDb, driver_id: str, pct: float | None) -> None:
    db.service(AccountService).update_driver(UUID(driver_id), {"commission_percent": pct})


def day_shift(
    db: TestDb, driver_id: str, day: str = "2026-10-01", start: str = "00:00", end: str = "23:59"
) -> str:
    """A closed shift covering most of a local day (+05:00). Shift ids are numbered within
    a test (the `shift_ids` fixture), so the first shift created in a test is sid(1)."""
    s = datetime.fromisoformat(f"{day}T{start}:00+05:00")
    e = datetime.fromisoformat(f"{day}T{end}:00+05:00")
    return str(db.service(ShiftService).start(UUID(driver_id), s, e, by_admin=True).id)
