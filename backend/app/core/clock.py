"""Current time, in one place so that tests can freeze it."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
