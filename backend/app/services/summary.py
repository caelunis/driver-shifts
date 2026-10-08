from collections.abc import Iterable
from datetime import date, datetime

from app.schemas.shifts import ShiftSummary
from app.schemas.trips import DaySummary, PaymentBreakdown, Totals, Trip


def totals(trips: Iterable[Trip]) -> Totals:
    cash = PaymentBreakdown()
    card = PaymentBreakdown()
    count = revenue = commission = 0
    for t in trips:
        count += 1
        revenue += t.amount
        commission += t.commission
        bucket = cash if t.payment == "cash" else card
        bucket.count += 1
        bucket.amount += t.amount
    return Totals(
        count=count, revenue=revenue, commission=commission, net=revenue - commission, cash=cash, card=card
    )


def day_summary(trips: Iterable[Trip], day: date, shifts: int) -> DaySummary:
    return DaySummary(date=day, shifts=shifts, **totals(trips).model_dump())


def shift_summary(trips: Iterable[Trip], start: datetime, end: datetime) -> ShiftSummary:
    """`end` is the shift's end, or now for an open shift."""
    t = totals(trips)
    minutes = int((end - start).total_seconds() // 60)
    per_hour = round(t.net * 60 / minutes) if minutes > 0 else None
    return ShiftSummary(duration_min=minutes, net_per_hour=per_hour, **t.model_dump())
