"""One-off start-up tasks, run by the `bootstrap` service after `dbmate up`:

- SEED_DEMO=1: demo accounts in an empty database (scripts/seed_demo.py);
- ADMIN_EMAIL + ADMIN_PASSWORD: the first real admin, if that e-mail is free.
"""
from app.core.config import get_settings
from app.core.db import open_pool
from app.services import accounts
from scripts.seed_demo import seed


def main() -> None:
    settings = get_settings()
    pool = open_pool(settings.database_url)
    try:
        if settings.seed_demo:
            print("Demo accounts created" if seed(pool) else "Accounts exist; demo seeding skipped")
        if settings.admin_email and settings.admin_password:
            created = accounts.ensure_admin(pool, settings.admin_email, settings.admin_password)
            print(f"Admin {settings.admin_email} {'created' if created else 'already exists'}")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
