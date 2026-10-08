from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import ErrorCode
from app.core.errors import DomainValidationError
from app.schemas.trips import TripIn


class Commission:
    """The commission of a trip, set by the admin as a percent or entered by the driver."""

    @staticmethod
    def for_fare(fare: int, percent: Decimal | float) -> int:
        """fare * percent / 100, rounded half up (Python's round() would round 352.5 to 352)."""
        exact = Decimal(fare) * Decimal(str(percent)) / 100
        return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @classmethod
    def resolve(cls, trip: TripIn, percent: Decimal | None) -> int:
        """The commission to store for this trip.

        With a percent the server computes it; a value the client sent is accepted only
        if it matches. Without a percent the driver enters it.
        """
        if percent is None:
            if trip.commission_amount is None:
                raise DomainValidationError("commission_amount", ErrorCode.MISSING, "Field required")
            return trip.commission_amount

        expected = cls.for_fare(trip.fare, percent)
        if trip.commission_amount is not None and trip.commission_amount != expected:
            raise DomainValidationError(
                "commission_amount",
                ErrorCode.COMMISSION_FIXED,
                f"Commission is set by the admin: {expected}",
                expected=expected,
                percent=float(percent),
            )
        if expected >= trip.fare:  # tiny fares, e.g. 1 KZT at 50% rounds up to 1
            raise DomainValidationError(
                "commission_amount",
                ErrorCode.COMMISSION_EXCEEDS_FARE,
                "Commission must be less than the fare",
            )
        return expected
