"""Domain models: what the services work with, independent of HTTP and SQL.

Repositories build them from rows; the API turns them into response schemas
(app/schemas, with from_attributes), so the wire format can change without
touching the rules, and the other way round.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.core.enums import PaymentMethod, Role, ShiftStatus

# --- accounts ---


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making the request: the account behind a live session."""

    id: UUID
    role: Role


@dataclass(frozen=True, slots=True)
class Credentials:
    id: UUID
    role: Role
    password_hash: str


@dataclass(frozen=True, slots=True)
class AccountProfile:
    """An account with its driver profile; the profile fields are None for admins."""

    id: UUID
    email: str
    role: Role
    full_name: str | None = None
    car_model: str | None = None
    car_plate: str | None = None
    timezone: str | None = None
    commission_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DriverOverview:
    """A driver as the admin's list shows them: profile plus totals."""

    id: UUID
    email: str
    role: Role
    full_name: str
    car_model: str
    car_plate: str | None
    timezone: str
    commission_percent: Decimal | None
    created_at: datetime
    trips_count: int
    revenue: int
    net_income: int
    last_work_date: dt.date | None


# --- shifts and trips ---


@dataclass(slots=True)
class Shift:
    id: UUID
    driver_id: UUID
    started_at: datetime
    ended_at: datetime | None  # None while the shift is open
    work_date: dt.date  # local date of the start, in the start's own offset
    note: str

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def status(self) -> ShiftStatus:
        return ShiftStatus.OPEN if self.ended_at is None else ShiftStatus.CLOSED


@dataclass(slots=True)
class Trip:
    id: UUID
    driver_id: UUID
    shift_id: UUID
    started_at: datetime
    ended_at: datetime
    fare: int
    payment_method: PaymentMethod
    commission_amount: int
    # The percent the commission was computed with; None if it was entered by hand
    commission_percent: Decimal | None = None

    @property
    def net_income(self) -> int:
        return self.fare - self.commission_amount

    def same_content(self, other: "Trip") -> bool:
        """Equal apart from the id. Aware datetimes compare by instant, not notation."""
        return (
            self.shift_id == other.shift_id
            and self.started_at == other.started_at
            and self.ended_at == other.ended_at
            and self.fare == other.fare
            and self.payment_method == other.payment_method
            and self.commission_amount == other.commission_amount
        )


# --- totals ---


@dataclass(slots=True)
class PaymentTotals:
    trips_count: int = 0
    amount: int = 0


@dataclass(slots=True)
class Totals:
    trips_count: int = 0
    revenue: int = 0
    commission_total: int = 0
    cash: PaymentTotals = field(default_factory=PaymentTotals)
    card: PaymentTotals = field(default_factory=PaymentTotals)

    @property
    def net_income(self) -> int:
        """Take-home: revenue minus commission."""
        return self.revenue - self.commission_total

    @classmethod
    def of(cls, trips: Iterable[Trip]) -> "Totals":
        totals = cls()
        for t in trips:
            totals.trips_count += 1
            totals.revenue += t.fare
            totals.commission_total += t.commission_amount
            bucket = totals.cash if t.payment_method == PaymentMethod.CASH else totals.card
            bucket.trips_count += 1
            bucket.amount += t.fare
        return totals

    def _fields(self) -> dict[str, object]:
        return {
            "trips_count": self.trips_count,
            "revenue": self.revenue,
            "commission_total": self.commission_total,
            "cash": self.cash,
            "card": self.card,
        }


@dataclass(slots=True)
class ShiftSummary(Totals):
    duration_minutes: int = 0  # up to now for an open shift
    net_income_per_hour: int | None = None  # None for a shift shorter than a minute

    @classmethod
    def for_shift(cls, trips: Iterable[Trip], started_at: datetime, ended_at: datetime) -> "ShiftSummary":
        """`ended_at` is the shift's end, or now for an open shift."""
        t = Totals.of(trips)
        minutes = int((ended_at - started_at).total_seconds() // 60)
        per_hour = round(t.net_income * 60 / minutes) if minutes > 0 else None
        return cls(**t._fields(), duration_minutes=minutes, net_income_per_hour=per_hour)  # type: ignore[arg-type]


@dataclass(slots=True)
class DaySummary(Totals):
    """Totals of all trips in the shifts that started on this work date."""

    work_date: dt.date = dt.date.min
    shifts_count: int = 0

    @classmethod
    def for_day(cls, work_date: dt.date, shifts_count: int, trips: Iterable[Trip]) -> "DaySummary":
        t = Totals.of(trips)
        return cls(**t._fields(), work_date=work_date, shifts_count=shifts_count)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class DayInfo:
    """A work date with at least one shift, for the calendar."""

    work_date: dt.date
    trips_count: int
    net_income: int


@dataclass(slots=True)
class ShiftReport:
    """A shift with its summary (and its trips, for the detailed view)."""

    shift: Shift
    summary: ShiftSummary
    trips: list[Trip]

    # Flattened for the response schemas, which read attributes
    @property
    def id(self) -> UUID:
        return self.shift.id

    @property
    def started_at(self) -> datetime:
        return self.shift.started_at

    @property
    def ended_at(self) -> datetime | None:
        return self.shift.ended_at

    @property
    def status(self) -> ShiftStatus:
        return self.shift.status

    @property
    def work_date(self) -> dt.date:
        return self.shift.work_date

    @property
    def note(self) -> str:
        return self.shift.note
