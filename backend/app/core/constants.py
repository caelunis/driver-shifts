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
# At least one letter (any alphabet) and one digit; length is checked separately
PASSWORD_STRENGTH_PATTERN = r"^(?=.*[^\W\d_])(?=.*\d)"  # noqa: S105 - a rule, not a password
# Profile fields a driver may change; everything else is managed by the admin
DRIVER_SELF_EDITABLE = frozenset({"timezone"})

# --- sessions and login ---
SESSION_COOKIE = "session"
SESSION_TTL = timedelta(days=30)
SESSION_TOKEN_BYTES = 32
LOGIN_MAX_FAILURES = 5  # failed logins per email, then a pause
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)

# --- API ---
API_PREFIX = "/api"
API_V1 = "/api/v1"  # the versioned API; /api/health stays unversioned for the infrastructure
API_VERSION = "1.0.0"

# --- access control and throttling ---
# The only API endpoints served without a session; every other path under /api needs one
PUBLIC_ENDPOINTS = frozenset(
    {
        ("POST", f"{API_V1}/auth/login"),
        ("POST", f"{API_V1}/auth/logout"),
        ("GET", f"{API_V1}/docs"),
        ("GET", f"{API_V1}/openapi.json"),
        ("GET", "/api/health"),
        ("HEAD", "/api/health"),
    }
)
# Requests per client address (not counting health checks)
THROTTLE_LIMIT = 600
THROTTLE_WINDOW = timedelta(minutes=1)
# Login attempts per client address, on top of the per-email limit above: stops one
# address from trying many different accounts
LOGIN_ATTEMPTS_PER_CLIENT = 60
LOGIN_ATTEMPTS_WINDOW = timedelta(minutes=5)
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
# Seconds a request waits for a pooled connection. Short: with the database down the
# request should fall back to the cache quickly instead of hanging
DB_ACQUIRE_TIMEOUT = 3.0
DB_RETRY_AFTER = 30  # seconds, the Retry-After of a 503 while the database is down
HEALTH_DB_TIMEOUT = 2.0

# --- cache ---
# A cached response is served as is for this long; afterwards it is refreshed. Writes
# through the API invalidate it at once, so this bounds only changes made outside the
# app and the "up to now" numbers of an open shift.
CACHE_FRESH_TTL = timedelta(seconds=30)
# How long a copy is kept to answer reads while the database is down
CACHE_STALE_TTL = timedelta(hours=24)
# The in-process fallback: shorter-lived (each app instance has its own) and bounded
CACHE_MEMORY_TTL_CAP = timedelta(seconds=30)
CACHE_MEMORY_MAX_ENTRIES = 10_000
# Sessions resolved from the cache before asking the database again
SESSION_CACHE_TTL = timedelta(seconds=60)
# Redis: fail fast, and after a failure use the fallback for a while before retrying
REDIS_TIMEOUT = 0.3  # seconds
REDIS_RETRY_AFTER = timedelta(seconds=10)
