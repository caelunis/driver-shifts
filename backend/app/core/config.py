from functools import lru_cache
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables and from .env if present
    (backend/.env or the repository's .env, the one docker compose uses).

    Database credentials have no defaults: a missing one is a startup error, not a
    silent connection to some default database.
    """

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    # Integration tests: a separate database on the same server
    postgres_test_db: str = "shifts_test"

    # Set COOKIE_SECURE=1 behind HTTPS; plain-HTTP localhost needs it off
    cookie_secure: bool = False

    # Used only by scripts/bootstrap.py, never by the running app
    seed_demo: bool = False
    admin_email: str = ""
    admin_password: str = ""

    def database_url(self, db: str | None = None) -> str:
        """libpq URL; `db` overrides the database name (the tests use their own)."""
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password.get_secret_value(), safe="")
        return (
            f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}"
            f"/{db or self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required fields come from the environment
