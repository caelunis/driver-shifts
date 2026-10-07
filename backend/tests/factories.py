"""Test helpers that create accounts through the same services the app uses."""
from psycopg_pool import ConnectionPool

from app.core.security import hash_password
from app.repositories import users as users_repo
from app.schemas.accounts import DriverCreate
from app.services import accounts


def create_driver(pool: ConnectionPool, email: str, password: str, name: str = "Водитель",
                  role: str = "driver", **profile) -> int:
    """A driver with a profile, or (role="admin" or anything else) a bare account."""
    if role == "driver":
        return accounts.create_driver(
            pool, DriverCreate(email=email, password=password, name=name, **profile))
    with pool.connection() as conn:
        return users_repo.insert(conn, email, hash_password(password), role)


def set_commission_pct(pool: ConnectionPool, driver_id: int, pct: float | None) -> None:
    accounts.update_driver(pool, driver_id, {"default_commission_pct": pct})
