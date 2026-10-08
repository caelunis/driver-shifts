"""Accounts: the driver's own profile and the admin's management of drivers."""

import asyncio
import logging
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from pydantic_core import PydanticCustomError

from app.core.enums import Role
from app.core.errors import DomainValidationError, NotFoundError
from app.core.logging import mask_email
from app.core.security import hash_password
from app.db.database import Database
from app.domain.models import AccountProfile, DriverOverview
from app.schemas.accounts import DriverCreate
from app.schemas.common import check_password

log = logging.getLogger(__name__)


def _pct(value: float | None) -> Decimal | None:
    # Through str: Decimal(12.3) would carry the float's binary error
    return None if value is None else Decimal(str(value))


class AccountService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- any account ---

    async def profile(self, user_id: int) -> AccountProfile:
        async with self._db.unit_of_work() as uow:
            profile = await uow.drivers.profile(user_id)
        if profile is None:
            raise NotFoundError()
        return profile

    async def set_timezone(self, driver_id: int, tz: str) -> AccountProfile:
        async with self._db.unit_of_work() as uow:
            await uow.drivers.update_profile(driver_id, {"default_tz": tz})
            profile = await uow.drivers.profile(driver_id)
        if profile is None:
            raise NotFoundError()
        log.info("timezone_changed", extra={"driver_id": driver_id, "tz": tz})
        return profile

    # --- drivers, managed by the admin ---

    async def create_driver(self, data: DriverCreate) -> DriverOverview:
        """The account and its profile in one transaction: both or neither."""
        password_hash = await asyncio.to_thread(hash_password, data.password)
        async with self._db.unit_of_work() as uow:
            user_id = await uow.users.insert(data.email, password_hash, Role.DRIVER)
            await uow.drivers.insert_profile(
                user_id,
                data.name,
                data.car_model,
                data.car_plate,
                data.default_tz,
                _pct(data.default_commission_pct),
            )
            driver = await uow.drivers.with_totals(user_id)
        assert driver is not None  # noqa: S101 - created just above, in the same transaction
        log.info("driver_created", extra={"driver_id": driver.id})
        return driver

    async def update_driver(self, driver_id: int, changes: Mapping[str, Any]) -> DriverOverview:
        """Apply profile changes; a new password also ends all of the driver's sessions."""
        changes = dict(changes)
        if "default_commission_pct" in changes:
            changes["default_commission_pct"] = _pct(changes["default_commission_pct"])
        password = changes.pop("password", None)
        new_hash = await asyncio.to_thread(hash_password, password) if password is not None else None
        async with self._db.unit_of_work() as uow:
            if password is not None:
                try:
                    check_password(password, await uow.users.email_of(driver_id))
                except PydanticCustomError as e:
                    raise DomainValidationError("password", e.type, e.message()) from e
            await uow.drivers.update_profile(driver_id, changes)
            if new_hash is not None:
                await uow.users.set_password_hash(driver_id, new_hash)
                await uow.sessions.delete_all_of(driver_id)
            driver = await uow.drivers.with_totals(driver_id)
        if driver is None:
            raise NotFoundError()
        # Field names only: values such as the password never reach the log
        log.info(
            "driver_updated",
            extra={
                "driver_id": driver_id,
                "fields": sorted(changes),
                "password_changed": new_hash is not None,
            },
        )
        return driver

    async def delete_driver(self, driver_id: int) -> bool:
        async with self._db.unit_of_work() as uow:
            deleted = await uow.users.delete_driver(driver_id)
        log.info("driver_deleted", extra={"driver_id": driver_id, "deleted": deleted})
        return deleted

    async def list_drivers(self, q: str | None = None) -> list[DriverOverview]:
        async with self._db.unit_of_work() as uow:
            return await uow.drivers.list_with_totals(q)

    async def get_driver(self, driver_id: int) -> DriverOverview | None:
        """A driver by id; None for unknown ids and for admin accounts."""
        async with self._db.unit_of_work() as uow:
            return await uow.drivers.with_totals(driver_id)

    # --- admins ---

    async def ensure_admin(self, email: str, password: str) -> bool:
        """Create an admin account unless the email is already taken. Returns True if created."""
        password_hash = await asyncio.to_thread(hash_password, password)
        async with self._db.unit_of_work() as uow:
            existing = await uow.users.credentials(email)
            if existing:
                if existing.role != Role.ADMIN:
                    # Never silently promote an existing driver account
                    log.warning("admin_not_created_driver_email", extra={"email": mask_email(email)})
                return False
            admin_id = await uow.users.insert(email, password_hash, Role.ADMIN)
        log.info("admin_created", extra={"admin_id": admin_id})
        return True

    async def any_accounts(self) -> bool:
        async with self._db.unit_of_work() as uow:
            return await uow.users.any_exist()
