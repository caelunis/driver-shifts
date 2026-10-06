import hashlib
import hmac
import os
import threading
import time

# scrypt parameters (RFC 7914 recommendations for interactive logins)
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, key = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    candidate = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p)
    )
    return hmac.compare_digest(candidate, bytes.fromhex(key))


class LoginLimiter:
    """Blocks an email after too many failed logins within a time window.

    In-memory and per process: enough for a single instance; several
    instances would need a shared store (e.g. a table or Redis).
    """

    def __init__(self, max_failures: int = 5, window_seconds: int = 15 * 60):
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
