import hashlib
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.constants import MAX_FARE, MAX_TRIP_DURATION, MIN_TRIP_DURATION, TRIP_ID_MAX_LENGTH
from app.core.enums import ErrorCode, PaymentMethod
from app.schemas.common import AwareDatetime, StrictModel


class TripIn(StrictModel):
    """Trip as sent by a client. The id is optional."""

    id: str | None = Field(default=None, min_length=1, max_length=TRIP_ID_MAX_LENGTH)
    shift_id: int = Field(gt=0)
    start: AwareDatetime
    end: AwareDatetime
    amount: int = Field(gt=0, le=MAX_FARE, description="Trip amount, KZT")
    payment: PaymentMethod
    # Omitted when the admin set a commission percent for the driver: the server computes it
    commission: int | None = Field(default=None, ge=0, description="Commission, KZT")

    # Cross-field checks are field validators rather than one model validator:
    # a model validator only runs when every field is valid, so the client would
    # see errors one at a time. Here each error is attached to its own field.
    # Custom error types let the client localize messages without parsing text.

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start")  # absent if start itself failed validation
        if start is None:
            return v
        if v <= start:
            raise PydanticCustomError(ErrorCode.END_BEFORE_START, "End must be later than start")
        if v - start < MIN_TRIP_DURATION:
            raise PydanticCustomError(ErrorCode.TRIP_TOO_SHORT, "A trip lasts at least a minute")
        if v - start > MAX_TRIP_DURATION:
            raise PydanticCustomError(
                ErrorCode.TRIP_TOO_LONG,
                "A trip lasts at most {hours} hours",
                {"hours": MAX_TRIP_DURATION // timedelta(hours=1)},
            )
        return v

    @field_validator("commission")
    @classmethod
    def commission_within_amount(cls, v: int | None, info: ValidationInfo) -> int | None:
        amount = info.data.get("amount")
        if v is not None and amount is not None and v >= amount:
            raise PydanticCustomError(
                ErrorCode.COMMISSION_EXCEEDS_AMOUNT, "Commission must be less than the trip amount"
            )
        return v

    def fingerprint(self) -> str:
        """Deterministic id derived from content, used when the client sends no id.

        Times are normalized to UTC so the same trip written with a different
        offset notation yields the same key.
        """
        raw = "|".join(
            [
                str(self.shift_id),
                self.start.astimezone(UTC).isoformat(),
                self.end.astimezone(UTC).isoformat(),
                str(self.amount),
                self.payment,
                str(self.commission),
            ]
        )
        return "auto-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_trip(self) -> "Trip":
        data = self.model_dump()
        data["id"] = self.id or self.fingerprint()
        return Trip(**data)


class TripPatch(StrictModel):
    """Changes to a stored trip; omitted fields keep their values. The id never changes."""

    shift_id: int | None = Field(default=None, gt=0)
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    amount: int | None = Field(default=None, gt=0, le=MAX_FARE)
    payment: PaymentMethod | None = None
    commission: int | None = Field(default=None, ge=0)

    # Validators run only on fields the client sent, so this rejects an explicit null
    # without making the field required. Cross-field rules are checked by the service
    # on the merged trip, since one side of the pair may come from the stored row.
    @field_validator("shift_id", "start", "end", "amount", "payment", "commission")
    @classmethod
    def not_null(cls, v):
        if v is None:
            raise PydanticCustomError(ErrorCode.NULL_NOT_ALLOWED, "Field cannot be null")
        return v


class Trip(TripIn):
    id: str
    commission: int  # always known once the trip is stored
    # The percent the commission was computed with; None if it was entered by hand
    commission_pct: float | None = None

    def same_content(self, other: "Trip") -> bool:
        # Aware datetimes compare by instant, not by how the offset is written
        return (
            self.shift_id == other.shift_id
            and self.start == other.start
            and self.end == other.end
            and self.amount == other.amount
            and self.payment == other.payment
            and self.commission == other.commission
        )


class PaymentBreakdown(BaseModel):
    count: int = 0
    amount: int = 0


class Totals(BaseModel):
    count: int
    revenue: int
    commission: int
    net: int  # take-home = revenue - commission
    cash: PaymentBreakdown
    card: PaymentBreakdown


class DaySummary(Totals):
    """Totals of all trips in the shifts that started on this local day."""

    date: date
    shifts: int


class DayInfo(BaseModel):
    """Short per-day entry for the day navigation panel: a day with at least one shift."""

    date: date
    count: int
    net: int
