from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from .common import CommissionPct, TzOffset

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


Role = Literal["driver", "admin"]


class Profile(BaseModel):
    """The logged-in account. Driver fields are None for admins: an admin is a
    user without a driver profile."""

    id: int
    email: str
    role: Role
    name: Optional[str] = None
    car: Optional[str] = None
    default_tz: Optional[str] = None
    default_commission_pct: Optional[float] = None


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

    name: str
    car: str
    default_tz: str
    created_at: datetime
    trips_count: int
    revenue: int
    net: int
    last_trip_day: Optional[date]
