from datetime import date, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.core.enums import PaymentMethod
from app.domain.models import DaySummary, ShiftSummary, Totals, Trip

DRIVER, SHIFT = uuid4(), uuid4()


def make(name, started_at, ended_at, fare, payment_method, commission_amount):
    return Trip(
        id=uuid5(NAMESPACE_URL, name),
        driver_id=DRIVER,
        shift_id=SHIFT,
        started_at=datetime.fromisoformat(started_at),
        ended_at=datetime.fromisoformat(ended_at),
        fare=fare,
        payment_method=PaymentMethod(payment_method),
        commission_amount=commission_amount,
    )


SAMPLE = [
    make("t1", "2026-10-01T08:10:00+05:00", "2026-10-01T08:32:00+05:00", 2400, "card", 360),
    make("t2", "2026-10-01T09:05:00+05:00", "2026-10-01T09:20:00+05:00", 1500, "cash", 225),
]


def test_totals_of_sample_trips():
    t = Totals.of(SAMPLE)
    assert (t.trips_count, t.revenue, t.commission_total, t.net_income) == (2, 3900, 585, 3315)
    assert (t.cash.trips_count, t.cash.amount) == (1, 1500)
    assert (t.card.trips_count, t.card.amount) == (1, 2400)


def test_no_trips_is_all_zeros():
    t = Totals.of([])
    assert t.trips_count == t.revenue == t.commission_total == t.net_income == 0
    assert t.cash.trips_count == t.card.trips_count == 0


def test_day_summary_carries_date_and_shift_count():
    s = DaySummary.for_day(date(2026, 10, 1), 2, SAMPLE)
    assert (s.work_date, s.shifts_count, s.net_income) == (date(2026, 10, 1), 2, 3315)


def test_shift_summary_duration_and_hourly_take_home():
    start = datetime.fromisoformat("2026-10-01T08:00:00+05:00")
    end = datetime.fromisoformat("2026-10-01T10:30:00+05:00")
    s = ShiftSummary.for_shift(SAMPLE, start, end)
    assert s.duration_minutes == 150
    assert s.net_income_per_hour == 1326  # 3315 per 2.5 h


def test_zero_length_shift_has_no_hourly_rate():
    t = datetime.fromisoformat("2026-10-01T08:00:00+05:00")
    assert ShiftSummary.for_shift([], t, t).net_income_per_hour is None
