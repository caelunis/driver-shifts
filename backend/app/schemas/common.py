from typing import Annotated

from pydantic import Field

# UTC offset as "+05:00"; real-world offsets range from -12:00 to +14:00
TzOffset = Annotated[str, Field(pattern=r"^[+-](0\d|1[0-4]):[0-5]\d$")]
# Below 100: commission must stay strictly less than the trip amount
CommissionPct = Annotated[float, Field(ge=0, lt=100)]
