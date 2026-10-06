import hashlib
from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

Payment = Literal["cash", "card"]


class TripIn(BaseModel):
    """Trip as sent by a client. The id is optional."""

    id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    start: datetime
    end: datetime
    amount: int = Field(gt=0, description="Trip amount, KZT")
    payment: Payment
    # Omitted when the admin set a commission percent for the driver: the server computes it
    commission: Optional[int] = Field(default=None, ge=0, description="Commission, KZT")

    # Cross-field checks are field validators rather than one model validator:
    # a model validator only runs when every field is valid, so the client would
    # see errors one at a time. Here each error is attached to its own field.
    # Custom error types let the client localize messages without parsing text.

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise PydanticCustomError(
                "timezone_required", "Timezone offset is required, e.g. +05:00"
            )
        return v

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start")  # absent if start itself failed validation
        if start is not None and v <= start:
            raise PydanticCustomError("end_before_start", "End must be later than start")
        return v

    @field_validator("commission")
    @classmethod
    def commission_within_amount(cls, v: Optional[int], info: ValidationInfo) -> Optional[int]:
        amount = info.data.get("amount")
        if v is not None and amount is not None and v >= amount:
            raise PydanticCustomError(
                "commission_exceeds_amount", "Commission must be less than the trip amount"
            )
        return v

    def fingerprint(self) -> str:
        """Deterministic id derived from content, used when the client sends no id.

        Times are normalized to UTC so the same trip written with a different
        offset notation yields the same key.
        """
        raw = "|".join([
            self.start.astimezone(timezone.utc).isoformat(),
            self.end.astimezone(timezone.utc).isoformat(),
            str(self.amount),
            self.payment,
            str(self.commission),
        ])
        return "auto-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_trip(self) -> "Trip":
        data = self.model_dump()
        data["id"] = self.id or self.fingerprint()
        return Trip(**data)


class Trip(TripIn):
    id: str
    commission: int  # always known once the trip is stored

    @property
    def local_day(self) -> date:
        # The day comes from the trip's own local start time (its offset), not UTC:
        # a trip at 02:00 +05:00 belongs to that day, not to the previous one.
        return self.start.date()

    def same_content(self, other: "Trip") -> bool:
        # Aware datetimes compare by instant, not by how the offset is written
        return (
            self.start == other.start
            and self.end == other.end
            and self.amount == other.amount
            and self.payment == other.payment
            and self.commission == other.commission
        )


class PaymentBreakdown(BaseModel):
    count: int = 0
    amount: int = 0


class DaySummary(BaseModel):
    date: date
    count: int
    revenue: int
    commission: int
    net: int  # take-home = revenue - commission
    cash: PaymentBreakdown
    card: PaymentBreakdown


class DayInfo(BaseModel):
    """Short per-day entry for the day navigation panel."""

    date: date
    count: int
    net: int


# --- accounts ---

# UTC offset as "+05:00"; real-world offsets range from -12:00 to +14:00
TzOffset = Annotated[str, Field(pattern=r"^[+-](0\d|1[0-4]):[0-5]\d$")]
# Below 100: commission must stay strictly less than the trip amount
CommissionPct = Annotated[float, Field(ge=0, lt=100)]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


Role = Literal["driver", "admin"]


class Profile(BaseModel):
    id: int
    email: str
    role: Role
    name: str
    car: str
    default_tz: str
    default_commission_pct: Optional[float]


def _clean_name(v):
    if v is None or not v.strip():
        raise PydanticCustomError("blank", "Name must not be blank")
    return v.strip()


class SelfProfileUpdate(BaseModel):
    """PATCH /api/me: a driver may change only their timezone."""

    default_tz: TzOffset


class DriverCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    car: str = Field(default="", max_length=100)
    default_tz: TzOffset = "+05:00"
    default_commission_pct: Optional[CommissionPct] = None

    _name = field_validator("name")(_clean_name)

    @field_validator("car")
    @classmethod
    def strip_car(cls, v: str) -> str:
        return v.strip()


class DriverUpdate(BaseModel):
    """PATCH /api/admin/drivers/{id}: only the fields that were sent are changed."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    car: Optional[str] = Field(default=None, max_length=100)
    default_tz: Optional[TzOffset] = None
    default_commission_pct: Optional[CommissionPct] = None  # null clears it
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

    _name = field_validator("name")(_clean_name)

    @field_validator("car", "default_tz", "password")
    @classmethod
    def not_null(cls, v, info: ValidationInfo):
        if v is None:
            raise PydanticCustomError("missing", "Field cannot be null")
        # Passwords are kept exactly as typed; text fields are trimmed
        return v if info.field_name == "password" else v.strip()


class DriverInfo(Profile):
    """A driver as the admin sees them: profile plus totals."""

    created_at: datetime
    trips_count: int
    revenue: int
    net: int
    last_trip_day: Optional[date]
