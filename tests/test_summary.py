from datetime import date

from app.models import Trip
from app.summary import day_index, summarize, trips_for_day


def make(id, start, end, amount, payment, commission):
    return Trip(id=id, start=start, end=end, amount=amount, payment=payment, commission=commission)


SAMPLE = [
    make("t1", "2026-10-01T08:10:00+05:00", "2026-10-01T08:32:00+05:00", 2400, "card", 360),
    make("t2", "2026-10-01T09:05:00+05:00", "2026-10-01T09:20:00+05:00", 1500, "cash", 225),
]


def test_summary_of_sample_day():
    s = summarize(SAMPLE, date(2026, 10, 1))
    assert s.count == 2
    assert s.revenue == 3900
    assert s.commission == 585
    assert s.net == 3315
    assert (s.cash.count, s.cash.amount) == (1, 1500)
    assert (s.card.count, s.card.amount) == (1, 2400)


def test_empty_day_is_all_zeros():
    s = summarize(SAMPLE, date(2026, 10, 5))
    assert s.count == s.revenue == s.commission == s.net == 0
    assert s.cash.count == s.card.count == 0


def test_other_days_are_excluded():
    trips = SAMPLE + [
        make("x", "2026-10-02T10:00:00+05:00", "2026-10-02T10:30:00+05:00", 9999, "card", 0),
    ]
    assert summarize(trips, date(2026, 10, 1)).revenue == 3900
    assert summarize(trips, date(2026, 10, 2)).revenue == 9999


def test_day_is_taken_from_local_time_not_utc():
    # 02:10 +05:00 is 21:10 UTC of the previous day; the trip must land on October 2
    night = make("n", "2026-10-02T02:10:00+05:00", "2026-10-02T02:35:00+05:00", 2800, "cash", 420)
    assert summarize([night], date(2026, 10, 2)).count == 1
    assert summarize([night], date(2026, 10, 1)).count == 0


def test_trip_over_midnight_belongs_to_start_day():
    t = make("m", "2026-10-01T23:40:00+05:00", "2026-10-02T00:15:00+05:00", 3200, "card", 480)
    assert summarize([t], date(2026, 10, 1)).count == 1
    assert summarize([t], date(2026, 10, 2)).count == 0


def test_trips_sorted_by_start():
    ids = [t.id for t in trips_for_day(list(reversed(SAMPLE)), date(2026, 10, 1))]
    assert ids == ["t1", "t2"]


def test_day_index_counts_and_net_per_day():
    trips = SAMPLE + [
        make("x", "2026-10-02T10:00:00+05:00", "2026-10-02T10:30:00+05:00", 1000, "card", 100),
    ]
    days = [(d.date.isoformat(), d.count, d.net) for d in day_index(trips)]
    assert days == [("2026-10-01", 2, 3315), ("2026-10-02", 1, 900)]
