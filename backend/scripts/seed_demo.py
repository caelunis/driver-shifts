"""Demo accounts for trying the app: a driver with sample trips and an admin.

    python -m scripts.seed_demo

Seeds only a database without any accounts, so it is safe to run on every start
and never brings back accounts that were deleted later.
"""
import json
from pathlib import Path

from psycopg_pool import ConnectionPool

from app.core.config import get_settings
from app.core.db import open_pool
from app.repositories import users as users_repo
from app.schemas.accounts import DriverCreate
from app.schemas.trips import TripIn
from app.services import accounts, trips

DEMO_TRIPS = Path(__file__).with_name("data") / "demo_trips.json"

DEMO_ADMIN = ("admin@example.com", "admin12345")
DEMO_DRIVERS = [
    # (account, sample trips file or None)
    (DriverCreate(email="demo@example.com", password="demo12345", name="Демо-водитель"), DEMO_TRIPS),
    (DriverCreate(email="erlan@example.com", password="erlan12345", name="Ерлан Сейтжанов",
                  car="Hyundai Accent, 777 AAA 02", default_commission_pct=15), None),
]


def seed(pool: ConnectionPool) -> bool:
    with pool.connection() as conn:
        if users_repo.any_exist(conn):
            return False
    accounts.ensure_admin(pool, *DEMO_ADMIN)
    for driver, trips_file in DEMO_DRIVERS:
        driver_id = accounts.create_driver(pool, driver)
        if trips_file:
            for item in json.loads(trips_file.read_text(encoding="utf-8")):
                trips.add(pool, driver_id, TripIn(**item))
    return True


def main() -> None:
    pool = open_pool(get_settings().database_url)
    try:
        print("Demo accounts created" if seed(pool) else "Accounts exist; demo seeding skipped")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
