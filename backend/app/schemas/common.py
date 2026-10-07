import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo, available_timezones

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.core.passwords import is_common


class StrictModel(BaseModel):
    """Base for request bodies: an unknown field is an error, not silently dropped
    (a typo like "ammount" would otherwise look like a successful request)."""

    model_config = ConfigDict(extra="forbid")


def _require_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise PydanticCustomError("timezone_required", "Timezone offset is required, e.g. +05:00")
    return v


# A datetime with an explicit UTC offset: the offset decides the local day
AwareDatetime = Annotated[datetime, AfterValidator(_require_tz)]

# Below 100: commission must stay strictly less than the trip amount
CommissionPct = Annotated[float, Field(ge=0, lt=100)]


@lru_cache(maxsize=1)
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _check_zone(v: str) -> str:
    if v not in _zones():
        raise PydanticCustomError("unknown_timezone", "Unknown timezone, expected e.g. Asia/Almaty")
    return v


# IANA timezone name. Unlike a fixed offset it follows the zone's rules over time
# (Kazakhstan, for one, moved to a single +05:00 zone in 2024).
IanaTz = Annotated[str, Field(max_length=64), AfterValidator(_check_zone)]


def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def _clean_text(v: str) -> str:
    """NFC-normalize, reject control and invisible formatting characters, collapse spaces."""
    if not isinstance(v, str):
        return v
    v = unicodedata.normalize("NFC", v)
    if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in v):
        raise PydanticCustomError("invalid_characters", "Contains control or invisible characters")
    return " ".join(v.split())


def _max_100(v: str) -> str:
    # Checked here rather than with Field(max_length): after the BeforeValidator pydantic
    # would report a generic "too_long" instead of the usual string error
    if len(v) > 100:
        raise PydanticCustomError("string_too_long",
                                  "String should have at most {max_length} characters",
                                  {"max_length": 100})
    return v


def _person_name(v: str) -> str:
    if not v:
        raise PydanticCustomError("blank", "Name must not be blank")
    if not any(ch.isalpha() for ch in v):
        raise PydanticCustomError("name_without_letters", "Name must contain letters")
    return _max_100(v)


# A person's name: letters required, surrounding and repeated spaces removed
PersonName = Annotated[str, BeforeValidator(_clean_text), AfterValidator(_person_name)]
# Free text that is shown to other people, e.g. a car model
CleanText = Annotated[str, BeforeValidator(_clean_text), AfterValidator(_max_100)]

# Kazakhstan plates since 2012: 3 digits, 2-3 letters, a 2-digit region code (01-20),
# e.g. 123 ABC 02. Cyrillic letters that look Latin are accepted and converted,
# since drivers type them on a Russian keyboard.
_LOOKALIKES = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")
_PLATE = re.compile(r"^\d{3}[A-Z]{2,3}(0[1-9]|1\d|20)$")


def _normalize_plate(v):
    if not isinstance(v, str):
        return v
    plate = re.sub(r"[\s-]", "", v).upper().translate(_LOOKALIKES)
    if not _PLATE.match(plate):
        raise PydanticCustomError("invalid_plate", "Expected a Kazakhstan plate, e.g. 123 ABC 02")
    return plate


# Stored without spaces, e.g. "123ABC02"
CarPlate = Annotated[str, BeforeValidator(_normalize_plate)]


def check_password(password: str, email: str | None) -> None:
    """Raises PydanticCustomError for a password that is easy to guess."""
    lowered = password.lower()
    if email and (lowered == email.lower() or lowered == email.split("@")[0].lower()):
        raise PydanticCustomError("password_like_email", "Password must differ from the email")
    if is_common(password):
        raise PydanticCustomError("password_too_common", "This password is too common")


Password = Annotated[str, Field(min_length=8, max_length=128)]
