from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables (and .env if present)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://shifts:shifts@127.0.0.1:5433/shifts"
    # Set COOKIE_SECURE=1 behind HTTPS; plain-HTTP localhost needs it off
    cookie_secure: bool = False

    # Used only by scripts/bootstrap.py, never by the running app
    seed_demo: bool = False
    admin_email: str = ""
    admin_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
