"""Domain models: what the services work with, independent of HTTP and SQL.

Repositories build them from rows; the API turns them into response schemas
(app/schemas, with from_attributes), so the wire format can change without
touching the rules, and the other way round.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.core.enums import PaymentMethod, Role, ShiftStatus

# --- accounts ---


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making the request: the account behind a live session."""

    id: int
    role: Role


@dataclass(frozen=True, slots=True)
class Credentials:
    id: int
    role: Role
    password_hash: str


@dataclass(frozen=True, slots=True)
class AccountProfile:
    """An account with its driver profile; the profile fields are None for admins."""

    id: int
    email: str
    role: Role
    name: str | None = None
    car_model: str | None = None
    car_plate: str | None = None
    default_tz: str | None = None
    default_commission_pct: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NewDriver:
    email: str
    password_hash: str
    name: str
    car_model: str
    car_plate: str | None
    default_tz: str
    default_commission_pct: Decimal | None


@dataclass(frozen=True, slots=True)
class DriverOverview:
    """A driver as the admin's list shows them: profile plus totals."""

    id: int
    email: str
    role: Role
    name: str
    car_model: str
    car_plate: str | None
    default_tz: str
    default_commission_pct: Decimal | None
    created_at: datetime
    trips_count: int
    revenue: int
    net: int
    last_trip_day: date | None


# --- shifts and trips ---


@dataclass(slots=True)
class Shift:
    id: int
    driver_id: int
    start: datetime
    end: datetime | None  # None while the shift is open
    local_day: date  # local day of the start, in the start's own offset
    note: str

    @property
    def is_open(self) -> bool:
        return self.end is None

    @property
    def status(self) -> ShiftStatus:
        return ShiftStatus.OPEN if self.end is None else ShiftStatus.CLOSED


@dataclass(slots=True)
class Trip:
    id: str
    driver_id: int
    shift_id: int
    start: datetime
    end: datetime
    amount: int
    payment: PaymentMethod
    commission: int
    # The percent the commission was computed with; None if it was entered by hand
    commission_pct: Decimal | None = None

    @property
    def net(self) -> int:
        return self.amount - self.commission

    def same_content(self, other: "Trip") -> bool:
        """Equal apart from the id. Aware datetimes compare by instant, not notation."""
        return (
            self.shift_id == other.shift_id
            and self.start == other.start
            and self.end == other.end
            and self.amount == other.amount
            and self.payment == other.payment
            and self.commission == other.commission
        )


# --- totals ---


@dataclass(slots=True)
class PaymentTotals:
    count: int = 0
    amount: int = 0


@dataclass(slots=True)
class Totals:
    count: int = 0
    revenue: int = 0
    commission: int = 0
    cash: PaymentTotals = field(default_factory=PaymentTotals)
    card: PaymentTotals = field(default_factory=PaymentTotals)

    @property
    def net(self) -> int:
        """Take-home: revenue minus commission."""
        return self.revenue - self.commission

    @classmethod
    def of(cls, trips: Iterable[Trip]) -> "Totals":
        totals = cls()
        for t in trips:
            totals.count += 1
            totals.revenue += t.amount
            totals.commission += t.commission
            bucket = totals.cash if t.payment == PaymentMethod.CASH else totals.card
            bucket.count += 1
            bucket.amount += t.amount
        return totals


@dataclass(slots=True)
class ShiftSummary(Totals):
    duration_min: int = 0  # up to now for an open shift
    net_per_hour: int | None = None  # None for a shift shorter than a minute

    @classmethod
    def for_shift(cls, trips: Iterable[Trip], start: datetime, end: datetime) -> "ShiftSummary":
        """`end` is the shift's end, or now for an open shift."""
        t = Totals.of(trips)
        minutes = int((end - start).total_seconds() // 60)
        per_hour = round(t.net * 60 / minutes) if minutes > 0 else None
        return cls(
            count=t.count,
            revenue=t.revenue,
            commission=t.commission,
            cash=t.cash,
            card=t.card,
            duration_min=minutes,
            net_per_hour=per_hour,
        )


@dataclass(slots=True)
class DaySummary(Totals):
    """Totals of all trips in the shifts that started on this local day."""

    date: dt.date = dt.date.min
    shifts: int = 0

    @classmethod
    def for_day(cls, day: dt.date, shifts: int, trips: Iterable[Trip]) -> "DaySummary":
        t = Totals.of(trips)
        return cls(
            count=t.count,
            revenue=t.revenue,
            commission=t.commission,
            cash=t.cash,
            card=t.card,
            date=day,
            shifts=shifts,
        )


@dataclass(frozen=True, slots=True)
class DayInfo:
    """A day with at least one shift, for the calendar."""

    date: dt.date
    count: int
    net: int


@dataclass(slots=True)
class ShiftReport:
    """A shift with its summary (and its trips, for the detailed view)."""

    shift: Shift
    summary: ShiftSummary
    trips: list[Trip]

    # Flattened for the response schemas, which read attributes
    @property
    def id(self) -> int:
        return self.shift.id

    @property
    def start(self) -> datetime:
        return self.shift.start

    @property
    def end(self) -> datetime | None:
        return self.shift.end

    @property
    def status(self) -> ShiftStatus:
        return self.shift.status

    @property
    def local_day(self) -> date:
        return self.shift.local_day

    @property
    def note(self) -> str:
        return self.shift.note
