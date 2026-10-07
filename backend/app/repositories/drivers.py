"""SQL for driver profiles (`drivers`, 1:1 with a `users` row of role 'driver')."""
from psycopg import Connection

from app.schemas.accounts import DriverInfo, Profile


def insert_profile(conn: Connection, user_id: int, name: str, car: str = "",
                   default_tz: str = "+05:00", default_commission_pct: float | None = None) -> None:
    conn.execute(
        "INSERT INTO drivers (user_id, name, car, default_tz, default_commission_pct)"
        " VALUES (%s, %s, %s, %s, %s)",
        (user_id, name, car, default_tz, default_commission_pct),
    )


def get_profile(conn: Connection, user_id: int) -> Profile | None:
    """Any account; driver fields stay None for admins (no profile row)."""
    row = conn.execute(
        "SELECT u.id, u.email, u.role, d.name, d.car, d.default_tz, d.default_commission_pct"
        " FROM users u LEFT JOIN drivers d ON d.user_id = u.id WHERE u.id = %s",
        (user_id,),
    ).fetchone()
    return Profile(**row) if row else None


def commission_pct(conn: Connection, driver_id: int) -> float | None:
    row = conn.execute(
        "SELECT default_commission_pct FROM drivers WHERE user_id = %s", (driver_id,)
    ).fetchone()
    return row["default_commission_pct"] if row else None


# Profile columns that may be updated (also guards the dynamic SQL below)
EDITABLE = ("name", "car", "default_tz", "default_commission_pct")


def update_profile(conn: Connection, driver_id: int, changes: dict) -> None:
    columns = {k: v for k, v in changes.items() if k in EDITABLE}
    if not columns:
        return
    assignments = ", ".join(f"{k} = %s" for k in columns)
    conn.execute(
        f"UPDATE drivers SET {assignments} WHERE user_id = %s", (*columns.values(), driver_id)
    )


# --- admin: drivers with totals ---

_WITH_TOTALS = """
    SELECT u.id, u.email, u.role, u.created_at,
           d.name, d.car, d.default_tz, d.default_commission_pct,
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


def list_with_totals(conn: Connection, q: str | None = None) -> list[DriverInfo]:
    """Drivers only: admins have no profile row, so the inner join leaves them out."""
    params: tuple = ()
    flt = ""
    if q and q.strip():
        flt = "WHERE d.name ILIKE %s OR u.email ILIKE %s OR d.car ILIKE %s"
        params = (_like(q.strip()),) * 3
    rows = conn.execute(_WITH_TOTALS.format(filter=flt), params).fetchall()
    return [DriverInfo(**r) for r in rows]


def get_with_totals(conn: Connection, driver_id: int) -> DriverInfo | None:
    row = conn.execute(_WITH_TOTALS.format(filter="WHERE d.user_id = %s"), (driver_id,)).fetchone()
    return DriverInfo(**row) if row else None
