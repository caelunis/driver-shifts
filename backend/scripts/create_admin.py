"""Create an admin account from the command line.

    python -m scripts.create_admin admin@company.kz
    docker compose run --rm bootstrap python -m scripts.create_admin admin@company.kz

The password is read interactively (or from stdin when piped), never from argv,
so it does not end up in shell history or the process list.
"""

import argparse
import getpass
import sys

from app.core.config import get_settings
from app.core.constants import PASSWORD_MIN_LENGTH
from app.core.db import open_pool
from app.services import accounts


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an admin account")
    parser.add_argument("email")
    args = parser.parse_args()

    if sys.stdin.isatty():
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match", file=sys.stderr)
            return 1
    else:
        password = sys.stdin.readline().rstrip("\n")
    if len(password) < PASSWORD_MIN_LENGTH:
        print(f"Password must be at least {PASSWORD_MIN_LENGTH} characters", file=sys.stderr)
        return 1

    pool = open_pool(get_settings().database_url())
    try:
        if not accounts.ensure_admin(pool, args.email, password):
            print(f"{args.email} already exists; nothing changed", file=sys.stderr)
            return 1
    finally:
        pool.close()
    print(f"Admin {args.email} created")
    return 0


if __name__ == "__main__":
    sys.exit(main())
