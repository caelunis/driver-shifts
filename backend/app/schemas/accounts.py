from datetime import date, datetime
from uuid import UUID

from pydantic import ConfigDict, EmailStr, Field, ValidationInfo, field_validator
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

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"email": "demo@example.com", "password": "demo12345"}]}
    )


class Profile(ResponseModel):
    """The logged-in account. Driver fields are null for admins: an admin is a
    user without a driver profile."""

    id: UUID
    email: str
    role: Role
    full_name: str | None = None
    car_model: str | None = None
    car_plate: str | None = Field(default=None, description='Normalized, e.g. "123ABC02"')
    timezone: str | None = Field(default=None, description="IANA name, e.g. Asia/Almaty")
    commission_percent: float | None = Field(
        default=None, description="Set by the admin; null: the driver enters each commission"
    )


class SelfProfileUpdate(StrictModel):
    """A driver may change only their timezone."""

    timezone: IanaTz


class DriverCreate(StrictModel):
    email: EmailStr
    password: Password = Field(description="8+ characters with a letter and a digit, not the email")
    full_name: PersonName
    car_model: CleanText = ""
    car_plate: CarPlate | None = Field(default=None, description="Kazakhstan plate, e.g. 123 ABC 02")
    timezone: IanaTz = DEFAULT_TZ
    commission_percent: CommissionPct | None = None

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str, info: ValidationInfo) -> str:
        check_password(v, info.data.get("email"))
        return v


class DriverUpdate(StrictModel):
    """Only the fields that were sent are changed."""

    full_name: PersonName | None = None
    car_model: CleanText | None = None
    car_plate: CarPlate | None = Field(default=None, description="null removes the plate")
    timezone: IanaTz | None = None
    commission_percent: CommissionPct | None = Field(default=None, description="null: the driver enters it")
    # Compared with the email by the service, which knows the stored one
    password: Password | None = Field(default=None, description="Ends all of the driver's sessions")

    @field_validator("full_name", "car_model", "timezone", "password")
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

    full_name: str
    car_model: str
    timezone: str
    created_at: datetime
    trips_count: int
    revenue: int
    net_income: int
    last_work_date: date | None = Field(description="The latest date with a trip")
