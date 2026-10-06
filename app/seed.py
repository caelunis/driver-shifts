import json
from pathlib import Path

from psycopg_pool import ConnectionPool

from .accounts import create_driver
from .models import TripIn
from .storage import TripStorage

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"


def seed_demo(pool: ConnectionPool, trips_file: Path) -> bool:
    """Create the demo driver with sample trips, but only in an empty database."""
    with pool.connection() as conn:
        if conn.execute("SELECT 1 FROM drivers LIMIT 1").fetchone():
            return False
    driver_id = create_driver(pool, DEMO_EMAIL, DEMO_PASSWORD, name="Демо-водитель")
    storage = TripStorage(pool)
    for item in json.loads(trips_file.read_text(encoding="utf-8")):
        storage.add(driver_id, TripIn(**item).to_trip())
    return True
