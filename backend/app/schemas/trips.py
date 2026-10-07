import hashlib
from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from .common import AwareDatetime

Payment = Literal["cash", "card"]


class TripIn(BaseModel):
    """Trip as sent by a client. The id is optional."""

    id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    shift_id: int = Field(gt=0)
    start: AwareDatetime
    end: AwareDatetime
    amount: int = Field(gt=0, description="Trip amount, KZT")
    payment: Payment
    # Omitted when the admin set a commission percent for the driver: the server computes it
    commission: Optional[int] = Field(default=None, ge=0, description="Commission, KZT")

    # Cross-field checks are field validators rather than one model validator:
    # a model validator only runs when every field is valid, so the client would
    # see errors one at a time. Here each error is attached to its own field.
    # Custom error types let the client localize messages without parsing text.

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
            str(self.shift_id),
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
