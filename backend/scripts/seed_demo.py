"""Demo accounts for trying the app: an admin and drivers, one with sample shifts.

    python -m scripts.seed_demo

Seeds only a database without any accounts, so it is safe to run on every start
and never brings back accounts that were deleted later.
"""

import json
from datetime import datetime
from pathlib import Path

from psycopg_pool import ConnectionPool

from app.core.config import get_settings
from app.core.db import open_pool
from app.repositories import users as users_repo
from app.schemas.accounts import DriverCreate
from app.schemas.trips import TripIn
from app.services import accounts, shifts, trips

DEMO_SHIFTS = Path(__file__).with_name("data") / "demo_shifts.json"

DEMO_ADMIN = ("admin@example.com", "admin12345")
# Demo credentials are public on purpose: they are printed in the README
DEMO_DRIVERS = [
    # (account, sample shifts file or None)
    (DriverCreate(email="demo@example.com", password="demo12345", name="Демо-водитель"), DEMO_SHIFTS),
    (
        DriverCreate(
            email="erlan@example.com",
            password="erlan12345",
            name="Ерлан Сейтжанов",
            car_model="Hyundai Accent",
            car_plate="777 AAA 02",
            default_commission_pct=15,
        ),
        None,
    ),
]


def _times(item: dict) -> tuple[datetime, datetime]:
    return datetime.fromisoformat(item["start"]), datetime.fromisoformat(item["end"])


def seed(pool: ConnectionPool) -> bool:
    with pool.connection() as conn:
        if users_repo.any_exist(conn):
            return False
    accounts.ensure_admin(pool, *DEMO_ADMIN)
    for driver, shifts_file in DEMO_DRIVERS:
        driver_id = accounts.create_driver(pool, driver)
        if shifts_file:
            for item in json.loads(shifts_file.read_text(encoding="utf-8")):
                # Sample data is dated in the past: added as the admin would, without
                # the driver's 7-day window
                shift = shifts.start(pool, driver_id, *_times(item), item["note"], by_admin=True)
                for trip in item["trips"]:
                    trips.add(pool, driver_id, TripIn(shift_id=shift.id, **trip), by_admin=True)
    return True


def main() -> None:
    pool = open_pool(get_settings().database_url())
    try:
        print("Demo accounts created" if seed(pool) else "Accounts exist; demo seeding skipped")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
