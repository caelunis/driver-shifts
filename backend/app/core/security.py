import hashlib
import hmac
import os
import threading
import time

from app.core.constants import (
    LOGIN_FAILURE_WINDOW,
    LOGIN_MAX_FAILURES,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
    SCRYPT_SALT_BYTES,
)


def hash_password(password: str) -> str:
    salt = os.urandom(SCRYPT_SALT_BYTES)
    key = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, key = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(candidate, bytes.fromhex(key))


class LoginLimiter:
    """Blocks an email after too many failed logins within a time window.

    In-memory and per process: enough for a single instance; several
    instances would need a shared store (e.g. a table or Redis).
    """

    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: int = int(LOGIN_FAILURE_WINDOW.total_seconds()),
    ):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        self._failures[key] = recent
        return recent

    def retry_after(self, key: str) -> int:
        """Seconds until the next attempt is allowed; 0 if not blocked."""
        with self._lock:
            now = time.monotonic()
            recent = self._recent(key, now)
            if len(recent) < self.max_failures:
                return 0
            return int(self.window - (now - recent[0])) + 1

    def failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._recent(key, now).append(now)

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
