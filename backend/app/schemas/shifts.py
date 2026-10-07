from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from .common import AwareDatetime
from .trips import Totals, Trip


class ShiftStartIn(BaseModel):
    """Start a shift now (no fields), at a given time, or enter a past shift (start + end)."""

    start: Optional[AwareDatetime] = None
    end: Optional[AwareDatetime] = None
    note: str = Field(default="", max_length=500)

    @field_validator("end")
    @classmethod
    def end_needs_start_and_after_it(cls, v, info: ValidationInfo):
        if v is None:
            return v
        start = info.data.get("start")
        if "start" in info.data and start is None:
            raise PydanticCustomError("start_required", "A past shift needs a start time")
        if start is not None and v <= start:
            raise PydanticCustomError("end_before_start", "End must be later than start")
        return v


class ShiftCloseIn(BaseModel):
    end: Optional[AwareDatetime] = None  # None = now


class ShiftSummary(Totals):
    duration_min: int            # up to now for an open shift
    net_per_hour: Optional[int]  # None for shifts shorter than a minute


class Shift(BaseModel):
    id: int
    start: datetime
    end: Optional[datetime]
    status: Literal["open", "closed"]
    local_day: date
    note: str
    summary: ShiftSummary


class ShiftDetail(Shift):
    trips: list[Trip]
