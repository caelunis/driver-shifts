"""Create an admin account from the command line.

    python -m app.create_admin admin@company.kz --name "Иван"
    docker compose exec app python -m app.create_admin admin@company.kz

The password is read interactively (or from stdin when piped), never from argv,
so it does not end up in shell history or the process list.
"""
import argparse
import getpass
import os
import sys

from .db import DEFAULT_DATABASE_URL, init_schema, open_pool
from .seed import ensure_admin


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an admin account")
    parser.add_argument("email")
    parser.add_argument("--name", default="Администратор")
    args = parser.parse_args()

    if sys.stdin.isatty():
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match", file=sys.stderr)
            return 1
    else:
        password = sys.stdin.readline().rstrip("\n")
    if len(password) < 8:
        print("Password must be at least 8 characters", file=sys.stderr)
        return 1

    pool = open_pool(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    try:
        init_schema(pool)
        if not ensure_admin(pool, args.email, password, name=args.name):
            print(f"{args.email} already exists; nothing changed", file=sys.stderr)
            return 1
    finally:
        pool.close()
    print(f"Admin {args.email} created")
    return 0


if __name__ == "__main__":
    sys.exit(main())
