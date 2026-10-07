from datetime import date, datetime
from typing import Literal, Optional

from pydantic import EmailStr, Field, ValidationInfo, field_validator
from pydantic import BaseModel
from pydantic_core import PydanticCustomError

from .common import (CarPlate, CleanText, CommissionPct, IanaTz, Password, PersonName,
                     StrictModel, check_password)

DEFAULT_TZ = "Asia/Almaty"


class LoginIn(StrictModel):
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
    car_model: Optional[str] = None
    car_plate: Optional[str] = None  # normalized, e.g. "123ABC02"
    default_tz: Optional[str] = None
    default_commission_pct: Optional[float] = None


class SelfProfileUpdate(StrictModel):
    """PATCH /api/me: a driver may change only their timezone."""

    default_tz: IanaTz


class DriverCreate(StrictModel):
    email: EmailStr
    password: Password
    name: PersonName
    car_model: CleanText = ""
    car_plate: Optional[CarPlate] = None
    default_tz: IanaTz = DEFAULT_TZ
    default_commission_pct: Optional[CommissionPct] = None

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str, info: ValidationInfo) -> str:
        check_password(v, info.data.get("email"))
        return v


class DriverUpdate(StrictModel):
    """PATCH /api/admin/drivers/{id}: only the fields that were sent are changed."""

    name: Optional[PersonName] = None
    car_model: Optional[CleanText] = None
    car_plate: Optional[CarPlate] = None              # null removes the plate
    default_tz: Optional[IanaTz] = None
    default_commission_pct: Optional[CommissionPct] = None  # null clears it
    # Compared with the email by the service, which knows the stored one
    password: Optional[Password] = None

    @field_validator("name", "car_model", "default_tz", "password")
    @classmethod
    def not_null(cls, v, info: ValidationInfo):
        # Runs only for fields the client sent: rejects an explicit null
        if v is None:
            raise PydanticCustomError("null_not_allowed", "Field cannot be null")
        if info.field_name == "password":
            check_password(v, None)
        return v


class DriverInfo(Profile):
    """A driver as the admin sees them: profile plus totals."""

    name: str
    car_model: str
    default_tz: str
    created_at: datetime
    trips_count: int
    revenue: int
    net: int
    last_trip_day: Optional[date]
