from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import AfterValidator, Field
from pydantic_core import PydanticCustomError


def _require_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise PydanticCustomError("timezone_required", "Timezone offset is required, e.g. +05:00")
    return v


# A datetime with an explicit UTC offset: the offset decides the local day
AwareDatetime = Annotated[datetime, AfterValidator(_require_tz)]

# UTC offset as "+05:00"; real-world offsets range from -12:00 to +14:00
TzOffset = Annotated[str, Field(pattern=r"^[+-](0\d|1[0-4]):[0-5]\d$")]
# Below 100: commission must stay strictly less than the trip amount
CommissionPct = Annotated[float, Field(ge=0, lt=100)]


def offset_tz(offset: str) -> timezone:
    """"+05:00" -> a fixed-offset tzinfo."""
    sign = -1 if offset[0] == "-" else 1
    hours, minutes = offset[1:].split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
