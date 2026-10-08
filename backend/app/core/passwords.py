"""Passwords that are guessed first (app/core/data/common_passwords.txt, one per line).

Only those of 8+ characters matter: shorter ones are rejected by length anyway.
Drawn from public breach top lists, plus local favourites.
"""

from functools import cache
from pathlib import Path

_LIST = Path(__file__).with_name("data") / "common_passwords.txt"


@cache
def _common() -> frozenset[str]:
    return frozenset(
        line.strip().lower() for line in _LIST.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def is_common(password: str) -> bool:
    lowered = password.lower()
    # A single repeated character ("aaaaaaaa") is as weak as anything on the list
    return lowered in _common() or len(set(lowered)) == 1
