import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo, available_timezones

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.core.constants import (
    CAR_MODEL_MAX_LENGTH,
    COMMISSION_PCT_MAX,
    NAME_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    PASSWORD_STRENGTH_PATTERN,
    PLATE_LOOKALIKES,
    PLATE_PATTERN,
    TZ_NAME_MAX_LENGTH,
)
from app.core.enums import ErrorCode
from app.core.passwords import is_common


class ResponseModel(BaseModel):
    """Base for responses. Built from domain objects (dataclasses) by attribute, and never
    re-validated against today's input rules: a row stored under older rules stays readable."""

    model_config = ConfigDict(from_attributes=True)


class StrictModel(BaseModel):
    """Base for request bodies: an unknown field is an error, not silently dropped
    (a typo like "ammount" would otherwise look like a successful request)."""

    model_config = ConfigDict(extra="forbid")


def _require_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise PydanticCustomError(ErrorCode.TIMEZONE_REQUIRED, "Timezone offset is required, e.g. +05:00")
    return v


# A datetime with an explicit UTC offset: the offset decides the local day
AwareDatetime = Annotated[datetime, AfterValidator(_require_tz)]

# Below 100: commission must stay strictly less than the trip amount
CommissionPct = Annotated[float, Field(ge=0, lt=COMMISSION_PCT_MAX)]


@lru_cache(maxsize=1)
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _check_zone(v: str) -> str:
    if v not in _zones():
        raise PydanticCustomError(ErrorCode.UNKNOWN_TIMEZONE, "Unknown timezone, expected e.g. Asia/Almaty")
    return v


# IANA timezone name. Unlike a fixed offset it follows the zone's rules over time
# (Kazakhstan, for one, moved to a single +05:00 zone in 2024).
IanaTz = Annotated[str, Field(max_length=TZ_NAME_MAX_LENGTH), AfterValidator(_check_zone)]


def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def _clean_text(v: object) -> object:
    """NFC-normalize, reject control and invisible formatting characters, collapse spaces.
    Non-strings pass through to the type check that follows."""
    if not isinstance(v, str):
        return v
    v = unicodedata.normalize("NFC", v)
    if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in v):
        raise PydanticCustomError(ErrorCode.INVALID_CHARACTERS, "Contains control or invisible characters")
    return " ".join(v.split())


def _max_length(limit: int) -> Callable[[str], str]:
    # Checked here rather than with Field(max_length): after the BeforeValidator pydantic
    # would report a generic "too_long" instead of the usual string error
    def check(v: str) -> str:
        if len(v) > limit:
            raise PydanticCustomError(
                ErrorCode.STRING_TOO_LONG,
                "String should have at most {max_length} characters",
                {"max_length": limit},
            )
        return v

    return check


def _person_name(v: str) -> str:
    if not v:
        raise PydanticCustomError(ErrorCode.BLANK, "Name must not be blank")
    if not any(ch.isalpha() for ch in v):
        raise PydanticCustomError(ErrorCode.NAME_WITHOUT_LETTERS, "Name must contain letters")
    return _max_length(NAME_MAX_LENGTH)(v)


# A person's name: letters required, surrounding and repeated spaces removed
PersonName = Annotated[str, BeforeValidator(_clean_text), AfterValidator(_person_name)]
# Free text that is shown to other people, e.g. a car model
CleanText = Annotated[str, BeforeValidator(_clean_text), AfterValidator(_max_length(CAR_MODEL_MAX_LENGTH))]

# Kazakhstan plates, e.g. 123 ABC 02. Cyrillic letters that look Latin are accepted
# and converted, since drivers type them on a Russian keyboard.
_LOOKALIKES = str.maketrans(*PLATE_LOOKALIKES)
_PLATE = re.compile(PLATE_PATTERN)


def _normalize_plate(v: object) -> object:
    if not isinstance(v, str):
        return v
    plate = re.sub(r"[\s-]", "", v).upper().translate(_LOOKALIKES)
    if not _PLATE.match(plate):
        raise PydanticCustomError(ErrorCode.INVALID_PLATE, "Expected a Kazakhstan plate, e.g. 123 ABC 02")
    return plate


# Stored without spaces, e.g. "123ABC02"
CarPlate = Annotated[str, BeforeValidator(_normalize_plate)]


_PASSWORD_STRENGTH = re.compile(PASSWORD_STRENGTH_PATTERN)


def check_password(password: str, email: str | None) -> None:
    """Raises PydanticCustomError for a password that is easy to guess."""
    lowered = password.lower()
    if email and (lowered == email.lower() or lowered == email.split("@")[0].lower()):
        raise PydanticCustomError(ErrorCode.PASSWORD_LIKE_EMAIL, "Password must differ from the email")
    if not _PASSWORD_STRENGTH.match(password):
        raise PydanticCustomError(
            ErrorCode.PASSWORD_TOO_WEAK, "Password needs at least one letter and one digit"
        )
    if is_common(password):
        raise PydanticCustomError(ErrorCode.PASSWORD_TOO_COMMON, "This password is too common")


Password = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
