from datetime import date, datetime

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.constants import NOTE_MAX_LENGTH
from app.core.enums import ErrorCode, ShiftStatus
from app.schemas.common import AwareDatetime, StrictModel
from app.schemas.trips import Totals, Trip


class ShiftStartIn(StrictModel):
    """Start a shift now (no fields), at a given time, or enter a past shift (start + end)."""

    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    note: str = Field(default="", max_length=NOTE_MAX_LENGTH)

    @field_validator("end")
    @classmethod
    def end_needs_start_and_after_it(cls, v, info: ValidationInfo):
        if v is None:
            return v
        start = info.data.get("start")
        if "start" in info.data and start is None:
            raise PydanticCustomError(ErrorCode.START_REQUIRED, "A past shift needs a start time")
        if start is not None and v <= start:
            raise PydanticCustomError(ErrorCode.END_BEFORE_START, "End must be later than start")
        return v


class ShiftCloseIn(StrictModel):
    end: AwareDatetime | None = None  # None = now


class ShiftPatch(StrictModel):
    """Changes to a shift; omitted fields keep their values. `end: null` reopens it."""

    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)

    @field_validator("start", "note")
    @classmethod
    def not_null(cls, v):
        # Runs only for fields the client sent: rejects an explicit null
        if v is None:
            raise PydanticCustomError(ErrorCode.NULL_NOT_ALLOWED, "Field cannot be null")
        return v


class ShiftSummary(Totals):
    duration_min: int  # up to now for an open shift
    net_per_hour: int | None  # None for shifts shorter than a minute


class Shift(BaseModel):
    id: int
    start: datetime
    end: datetime | None
    status: ShiftStatus
    local_day: date
    note: str
    summary: ShiftSummary


class ShiftDetail(Shift):
    trips: list[Trip]
