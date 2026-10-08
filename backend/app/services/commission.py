from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import ErrorCode
from app.core.errors import DomainValidationError
from app.schemas.trips import TripIn


class Commission:
    """The commission of a trip, set by the admin as a percent or entered by the driver."""

    @staticmethod
    def for_amount(amount: int, pct: Decimal | float) -> int:
        """amount * pct / 100, rounded half up (Python's round() would round 352.5 to 352)."""
        exact = Decimal(amount) * Decimal(str(pct)) / 100
        return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @classmethod
    def resolve(cls, trip: TripIn, pct: Decimal | None) -> int:
        """The commission to store for this trip.

        With a percent the server computes it; a value the client sent is accepted only
        if it matches. Without a percent the driver enters it.
        """
        if pct is None:
            if trip.commission is None:
                raise DomainValidationError("commission", ErrorCode.MISSING, "Field required")
            return trip.commission

        expected = cls.for_amount(trip.amount, pct)
        if trip.commission is not None and trip.commission != expected:
            raise DomainValidationError(
                "commission",
                ErrorCode.COMMISSION_FIXED,
                f"Commission is set by the admin: {expected}",
                expected=expected,
                pct=float(pct),
            )
        if expected >= trip.amount:  # tiny amounts, e.g. 1 KZT at 50% rounds up to 1
            raise DomainValidationError(
                "commission",
                ErrorCode.COMMISSION_EXCEEDS_AMOUNT,
                "Commission must be less than the trip amount",
            )
        return expected
