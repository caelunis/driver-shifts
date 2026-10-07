from datetime import date
from typing import Iterable

from app.schemas.trips import DaySummary, PaymentBreakdown, Trip


def trips_for_day(trips: Iterable[Trip], day: date) -> list[Trip]:
    return sorted((t for t in trips if t.local_day == day), key=lambda t: t.start)


def summarize(trips: Iterable[Trip], day: date) -> DaySummary:
    day_trips = trips_for_day(trips, day)
    cash = PaymentBreakdown()
    card = PaymentBreakdown()
    revenue = commission = 0

    for t in day_trips:
        revenue += t.amount
        commission += t.commission
        bucket = cash if t.payment == "cash" else card
        bucket.count += 1
        bucket.amount += t.amount

    return DaySummary(
        date=day,
        count=len(day_trips),
        revenue=revenue,
        commission=commission,
        net=revenue - commission,
        cash=cash,
        card=card,
    )

