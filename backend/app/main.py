from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool

from app.api import errors
from app.api.routes import auth, health, me, shifts, trips
from app.api.routes.admin import drivers as admin_drivers
from app.core.config import get_settings
from app.core.db import open_pool
from app.core.security import LoginLimiter

# Temporary: the current single-page client, until the separate frontend app replaces it
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(pool: ConnectionPool | None = None) -> FastAPI:
    """Pass a pool in tests; otherwise the app connects to DATABASE_URL on startup.

    The app never creates or changes the schema: run `dbmate up` first.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pool is not None:
            yield
            return
        app.state.pool = open_pool(get_settings().database_url)
        try:
            yield
        finally:
            app.state.pool.close()

    app = FastAPI(title="Driver shift diary", lifespan=lifespan)
    if pool is not None:
        app.state.pool = pool
    app.state.login_limiter = LoginLimiter()

    errors.install(app)

    for router in (health.router, auth.router, me.router, shifts.router, trips.router,
                   admin_drivers.router):
        app.include_router(router)

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
