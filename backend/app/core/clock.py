"""Current time, in one place so that tests can freeze it."""
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)
