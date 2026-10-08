from datetime import date, datetime
from uuid import UUID

from pydantic import ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.constants import NOTE_MAX_LENGTH
from app.core.enums import ErrorCode, ShiftStatus
from app.schemas.common import AwareDatetime, ResponseModel, StrictModel
from app.schemas.trips import Totals, Trip


class ShiftStartIn(StrictModel):
    """Start a shift now (empty body), at a given time, or enter a finished past shift."""

    started_at: AwareDatetime | None = Field(default=None, description="Omitted: now")
    ended_at: AwareDatetime | None = Field(
        default=None, description="Given: a finished past shift, at most 24 hours long"
    )
    note: str = Field(default="", max_length=NOTE_MAX_LENGTH)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {},
                {
                    "started_at": "2026-10-01T08:00:00+05:00",
                    "ended_at": "2026-10-01T18:00:00+05:00",
                    "note": "Day",
                },
            ]
        }
    )

    @field_validator("ended_at")
    @classmethod
    def needs_start_and_comes_after_it(cls, v: datetime | None, info: ValidationInfo) -> datetime | None:
        if v is None:
            return v
        started_at = info.data.get("started_at")
        if "started_at" in info.data and started_at is None:
            raise PydanticCustomError(ErrorCode.START_REQUIRED, "A past shift needs a start time")
        if started_at is not None and v <= started_at:
            raise PydanticCustomError(ErrorCode.END_BEFORE_START, "End must be later than start")
        return v


class ShiftCloseIn(StrictModel):
    ended_at: AwareDatetime | None = Field(default=None, description="Omitted: now")


class ShiftPatch(StrictModel):
    """Changes to a shift; omitted fields keep their values. `ended_at: null` reopens it."""

    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)

    @field_validator("started_at", "note")
    @classmethod
    def not_null(cls, v: object) -> object:
        # Runs only for fields the client sent: rejects an explicit null
        if v is None:
            raise PydanticCustomError(ErrorCode.NULL_NOT_ALLOWED, "Field cannot be null")
        return v


class ShiftSummary(Totals):
    duration_minutes: int = Field(description="Up to now for an open shift")
    net_income_per_hour: int | None = Field(description="null for a shift shorter than a minute")


class Shift(ResponseModel):
    id: UUID
    started_at: datetime
    ended_at: datetime | None = Field(description="null while the shift is open")
    status: ShiftStatus
    work_date: date = Field(description="The local date the shift started on; its trips count there")
    note: str
    summary: ShiftSummary


class ShiftDetail(Shift):
    trips: list[Trip]
