"""Identifiers: UUIDv7 for new rows, UUIDv5 for trips sent without an id."""

import os
import time
from uuid import UUID, uuid5

# Namespace for ids derived from a trip's content (a fixed, arbitrary UUID)
TRIP_CONTENT_NAMESPACE = UUID("6f1d2b3c-0c4e-4a8e-9d7b-5c1a2e3f4b6d")


def uuid7() -> UUID:
    """A time-ordered UUID (RFC 9562, version 7): 48 bits of Unix milliseconds, then random.

    Ids created later sort later, so a primary-key index grows at its end instead of
    taking inserts all over the tree as random (v4) ids do. Python's uuid module gains
    uuid7() only in 3.14.
    """
    millis = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10))  # 80 random bits, 74 of them used
    value = (millis & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= (rand >> 68) << 64 & (0xFFF << 64)  # 12 random bits (rand_a)
    value |= 0b10 << 62  # RFC 4122 variant
    value |= rand & ((1 << 62) - 1)  # 62 random bits (rand_b)
    return UUID(int=value)


def content_id(*parts: object) -> UUID:
    """A stable UUID for the same content: a retried request maps to the same id."""
    return uuid5(TRIP_CONTENT_NAMESPACE, "|".join(str(p) for p in parts))
