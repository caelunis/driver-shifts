"""Every business limit and tunable value of the app, in one place.

The frontend mirrors some of them (frontend/src/features/*/schema.ts); the server
stays the authority.
"""

from datetime import timedelta

# --- shifts ---
MAX_SHIFT = timedelta(hours=24)
# How far back a driver may enter or change shifts; the admin is not limited
BACKFILL_WINDOW = timedelta(days=7)
# Tolerance for client clocks that run slightly ahead
CLOCK_SKEW = timedelta(minutes=5)
NOTE_MAX_LENGTH = 500

# --- trips ---
MAX_FARE = 500_000  # KZT; a typo guard, far above any real fare
MIN_TRIP_DURATION = timedelta(minutes=1)
MAX_TRIP_DURATION = timedelta(hours=6)
TRIP_ID_MAX_LENGTH = 64
# Commission is a percent below 100: a trip always leaves the driver something
COMMISSION_PCT_MAX = 100

# --- accounts ---
DEFAULT_TZ = "Asia/Almaty"
TZ_NAME_MAX_LENGTH = 64
NAME_MAX_LENGTH = 100
CAR_MODEL_MAX_LENGTH = 100
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
# Profile fields a driver may change; everything else is managed by the admin
DRIVER_SELF_EDITABLE = frozenset({"default_tz"})

# --- sessions and login ---
SESSION_COOKIE = "session"
SESSION_TTL = timedelta(days=30)
SESSION_TOKEN_BYTES = 32
LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
# scrypt parameters (RFC 7914 recommendations for interactive logins)
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SCRYPT_SALT_BYTES = 16

# --- Kazakhstan plates (since 2012): 3 digits, 2-3 letters, region 01-20 ---
PLATE_PATTERN = r"^\d{3}[A-Z]{2,3}(0[1-9]|1\d|20)$"
# Cyrillic letters that look Latin, as typed on a Russian keyboard
PLATE_LOOKALIKES = ("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")

# --- infrastructure ---
DB_POOL_MIN_SIZE = 1
DB_POOL_MAX_SIZE = 10
DB_CONNECT_TIMEOUT = 10.0  # seconds to wait for the database on startup
HEALTH_DB_TIMEOUT = 2.0
