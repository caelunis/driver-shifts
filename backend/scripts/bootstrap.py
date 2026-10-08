"""One-off start-up tasks, run by the `bootstrap` service after `dbmate up`:

- SEED_DEMO=1: demo accounts in an empty database (scripts/seed_demo.py);
- ADMIN_EMAIL + ADMIN_PASSWORD: the first real admin, if that e-mail is free.
"""

import asyncio

from app.cache.store import Cache
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.database import Database
from app.services.accounts import AccountService
from scripts.seed_demo import seed


async def main() -> None:
    settings = get_settings()
    db = await Database.connect(settings.database_url())
    try:
        if settings.seed_demo:
            print("Demo accounts created" if await seed(db) else "Accounts exist; demo seeding skipped")
        if settings.admin_email and settings.admin_password:
            created = await AccountService(db, Cache.in_process()).ensure_admin(
                settings.admin_email, settings.admin_password
            )
            print(f"Admin {settings.admin_email} {'created' if created else 'already exists'}")
    finally:
        await db.close()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
