import hashlib
import hmac
import os

from app.core.constants import (
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
