"""Closed sets of values. StrEnum members are plain strings on the wire and in the database."""

from enum import StrEnum


class Role(StrEnum):
    DRIVER = "driver"
    ADMIN = "admin"


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"


class ShiftStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ErrorCode(StrEnum):
    """Stable error codes of the API (the `code` of an error and of a field error).

    Clients translate them; the English message is only a fallback.
    """

    # request as a whole
    VALIDATION_ERROR = "validation_error"
    NOT_AUTHENTICATED = "not_authenticated"
    INVALID_CREDENTIALS = "invalid_credentials"
    TOO_MANY_ATTEMPTS = "too_many_attempts"
    DRIVERS_ONLY = "drivers_only"
    ADMINS_ONLY = "admins_only"
    ADMIN_MANAGED_FIELDS = "admin_managed_fields"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    NOT_FOUND = "not_found"
    DRIVER_NOT_FOUND = "driver_not_found"
    DB_UNAVAILABLE = "db_unavailable"
    INTERNAL_ERROR = "internal_error"

    # conflicts with the current state
    SHIFT_ALREADY_OPEN = "shift_already_open"
    SHIFT_ALREADY_CLOSED = "shift_already_closed"
    SHIFT_OVERLAP = "shift_overlap"
    SHIFT_LOCKED = "shift_locked"
    TRIP_OVERLAP = "trip_overlap"
    TRIP_CONFLICT = "trip_conflict"
    TRIP_CHANGED = "trip_changed"
    EMAIL_TAKEN = "email_taken"
    PLATE_TAKEN = "plate_taken"

    # field errors
    MISSING = "missing"
    BLANK = "blank"
    NULL_NOT_ALLOWED = "null_not_allowed"
    STRING_TOO_LONG = "string_too_long"
    TIMEZONE_REQUIRED = "timezone_required"
    UNKNOWN_TIMEZONE = "unknown_timezone"
    INVALID_CHARACTERS = "invalid_characters"
    NAME_WITHOUT_LETTERS = "name_without_letters"
    INVALID_PLATE = "invalid_plate"
    PASSWORD_TOO_COMMON = "password_too_common"  # noqa: S105 - an error code, not a password
    PASSWORD_LIKE_EMAIL = "password_like_email"  # noqa: S105
    END_BEFORE_START = "end_before_start"
    START_REQUIRED = "start_required"
    TRIP_TOO_SHORT = "trip_too_short"
    TRIP_TOO_LONG = "trip_too_long"
    SHIFT_NOT_FOUND = "shift_not_found"
    OUTSIDE_SHIFT = "outside_shift"
    IN_FUTURE = "in_future"
    TOO_OLD = "too_old"
    SHIFT_TOO_LONG = "shift_too_long"
    BEFORE_LAST_TRIP = "before_last_trip"
    AFTER_FIRST_TRIP = "after_first_trip"
    COMMISSION_FIXED = "commission_fixed"
    COMMISSION_EXCEEDS_AMOUNT = "commission_exceeds_amount"
