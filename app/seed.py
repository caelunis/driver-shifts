import json
import logging
from pathlib import Path

from psycopg_pool import ConnectionPool

from .accounts import create_driver
from .models import TripIn
from .storage import TripStorage

log = logging.getLogger(__name__)

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"
DEMO_ADMIN_EMAIL = "admin@example.com"
DEMO_ADMIN_PASSWORD = "admin12345"


def ensure_admin(pool: ConnectionPool, email: str, password: str, name: str = "Администратор") -> bool:
    """Create an admin account unless the email is already taken. Returns True if created."""
    with pool.connection() as conn:
        existing = conn.execute(
            "SELECT role FROM drivers WHERE lower(email) = lower(%s)", (email,)
        ).fetchone()
    if existing:
        if existing["role"] != "admin":
            # Never silently promote an existing driver account
            log.warning("ADMIN_EMAIL %s belongs to a driver account; admin not created", email)
        return False
    create_driver(pool, email, password, name=name, role="admin")
    return True


def seed_demo(pool: ConnectionPool, trips_file: Path) -> None:
    """Demo driver with sample trips, only in a completely empty database (so a driver
    the admin deleted does not come back on restart), plus the demo admin if missing
    (also added to databases created before admins existed)."""
    with pool.connection() as conn:
        empty = conn.execute("SELECT 1 FROM drivers LIMIT 1").fetchone() is None
    if empty:
        driver_id = create_driver(pool, DEMO_EMAIL, DEMO_PASSWORD, name="Демо-водитель")
        storage = TripStorage(pool)
        for item in json.loads(trips_file.read_text(encoding="utf-8")):
            storage.add(driver_id, TripIn(**item).to_trip())
    ensure_admin(pool, DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD)
