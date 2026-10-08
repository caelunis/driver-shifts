from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from app.api import errors
from app.api.routes import auth, health, me, shifts, trips
from app.api.routes.admin import drivers as admin_drivers
from app.core.config import get_settings
from app.core.db import open_pool
from app.core.security import LoginLimiter


def create_app(pool: ConnectionPool | None = None) -> FastAPI:
    """Pass a pool in tests; otherwise the app connects to the POSTGRES_* database on startup.

    The app never creates or changes the schema: run `dbmate up` first.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pool is not None:
            yield
            return
        app.state.pool = open_pool(get_settings().database_url())
        try:
            yield
        finally:
            app.state.pool.close()

    # Everything under /api: the frontend's nginx proxies only that prefix
    app = FastAPI(
        title="Driver shift diary",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    if pool is not None:
        app.state.pool = pool
    app.state.login_limiter = LoginLimiter()

    errors.install(app)

    for router in (health.router, auth.router, me.router, shifts.router, trips.router, admin_drivers.router):
        app.include_router(router)

    return app


app = create_app()
