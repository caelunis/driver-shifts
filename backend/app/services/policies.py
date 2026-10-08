"""Rules about time that shifts and trips share."""

from datetime import datetime, timedelta

from app.core import clock
from app.core.constants import BACKFILL_WINDOW, CLOCK_SKEW, MAX_SHIFT
from app.core.enums import ErrorCode
from app.core.errors import ConflictError, DomainValidationError
from app.domain.models import Shift

MAX_SHIFT_HOURS = MAX_SHIFT // timedelta(hours=1)


class ShiftPolicy:
    """What may be entered or changed, and when. Raises a domain error otherwise."""

    @staticmethod
    def not_in_future(field: str, value: datetime) -> None:
        if value > clock.now() + CLOCK_SKEW:
            raise DomainValidationError(field, ErrorCode.IN_FUTURE, "Time is in the future")

    @staticmethod
    def within_window(field: str, value: datetime) -> None:
        """Drivers enter and change only the last 7 days; the admin is not limited."""
        if value < clock.now() - BACKFILL_WINDOW:
            raise DomainValidationError(
                field, ErrorCode.TOO_OLD, "Older than the allowed window", days=BACKFILL_WINDOW.days
            )

    @staticmethod
    def editable_by_driver(shift: Shift) -> None:
        """A driver may change a shift and its trips while it is open or for 7 days after
        it ended; older shifts are only changed by the admin."""
        if shift.ended_at is not None and shift.ended_at < clock.now() - BACKFILL_WINDOW:
            raise ConflictError(
                ErrorCode.SHIFT_LOCKED, "The shift ended more than 7 days ago", days=BACKFILL_WINDOW.days
            )

    @classmethod
    def valid_end(cls, started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            raise DomainValidationError(
                "ended_at", ErrorCode.END_BEFORE_START, "End must be later than start"
            )
        if ended_at - started_at > MAX_SHIFT:
            raise DomainValidationError(
                "ended_at", ErrorCode.SHIFT_TOO_LONG, "A shift lasts at most 24 hours", hours=MAX_SHIFT_HOURS
            )
        cls.not_in_future("ended_at", ended_at)

    @staticmethod
    def not_longer_than_max(field: str, started_at: datetime) -> None:
        """An open shift started at `started_at` must not already exceed the maximum."""
        if clock.now() - started_at > MAX_SHIFT:
            raise DomainValidationError(
                field, ErrorCode.SHIFT_TOO_LONG, "A shift lasts at most 24 hours", hours=MAX_SHIFT_HOURS
            )
