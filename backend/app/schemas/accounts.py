from datetime import date, datetime

from pydantic import EmailStr, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.constants import DEFAULT_TZ, PASSWORD_MAX_LENGTH
from app.core.enums import ErrorCode, Role
from app.schemas.common import (
    CarPlate,
    CleanText,
    CommissionPct,
    IanaTz,
    Password,
    PersonName,
    ResponseModel,
    StrictModel,
    check_password,
)


class LoginIn(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class Profile(ResponseModel):
    """The logged-in account. Driver fields are None for admins: an admin is a
    user without a driver profile."""

    id: int
    email: str
    role: Role
    name: str | None = None
    car_model: str | None = None
    car_plate: str | None = None  # normalized, e.g. "123ABC02"
    default_tz: str | None = None
    default_commission_pct: float | None = None


class SelfProfileUpdate(StrictModel):
    """PATCH /api/me: a driver may change only their timezone."""

    default_tz: IanaTz


class DriverCreate(StrictModel):
    email: EmailStr
    password: Password
    name: PersonName
    car_model: CleanText = ""
    car_plate: CarPlate | None = None
    default_tz: IanaTz = DEFAULT_TZ
    default_commission_pct: CommissionPct | None = None

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str, info: ValidationInfo) -> str:
        check_password(v, info.data.get("email"))
        return v


class DriverUpdate(StrictModel):
    """PATCH /api/admin/drivers/{id}: only the fields that were sent are changed."""

    name: PersonName | None = None
    car_model: CleanText | None = None
    car_plate: CarPlate | None = None  # null removes the plate
    default_tz: IanaTz | None = None
    default_commission_pct: CommissionPct | None = None  # null clears it
    # Compared with the email by the service, which knows the stored one
    password: Password | None = None

    @field_validator("name", "car_model", "default_tz", "password")
    @classmethod
    def not_null(cls, v: str | None, info: ValidationInfo) -> str:
        # Runs only for fields the client sent: rejects an explicit null
        if v is None:
            raise PydanticCustomError(ErrorCode.NULL_NOT_ALLOWED, "Field cannot be null")
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
    last_trip_day: date | None
