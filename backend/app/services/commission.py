from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import DomainValidationError
from app.schemas.trips import TripIn


def commission_for(amount: int, pct: float) -> int:
    """amount * pct / 100, rounded half up (Python's round() would round 352.5 to 352)."""
    exact = Decimal(amount) * Decimal(str(pct)) / 100
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def resolve_commission(trip: TripIn, pct: float | None) -> TripIn:
    """Fill in the trip's commission according to the driver's profile.

    With a percent set by the admin the server computes the commission; a client
    value is accepted only if it matches. Without a percent the driver enters it.
    """
    if pct is None:
        if trip.commission is None:
            raise DomainValidationError("commission", "missing", "Field required")
        return trip

    expected = commission_for(trip.amount, pct)
    if trip.commission is not None and trip.commission != expected:
        raise DomainValidationError("commission", "commission_fixed",
                                    f"Commission is set by the admin: {expected}",
                                    expected=expected, pct=pct)
    if expected >= trip.amount:  # tiny amounts, e.g. 1 KZT at 50% rounds up to 1
        raise DomainValidationError("commission", "commission_exceeds_amount",
                                    "Commission must be less than the trip amount")
    return trip.model_copy(update={"commission": expected})
