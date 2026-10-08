from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import errors
from app.api.middleware import RequestContextMiddleware
from app.api.routers import auth, health, me, shifts, trips
from app.api.routers.admin import drivers as admin_drivers
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import LoginLimiter
from app.db.database import Database


def create_app(db: Database | None = None) -> FastAPI:
    """Pass a database in tests; otherwise the app connects to the POSTGRES_* database on startup.

    The app never creates or changes the schema: run `dbmate up` first.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if db is not None:
            yield
            return
        app.state.db = await Database.connect(get_settings().database_url())
        try:
            yield
        finally:
            await app.state.db.close()

    # Everything under /api: the frontend's nginx proxies only that prefix
    app = FastAPI(
        title="Driver shift diary",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    if db is not None:
        app.state.db = db
    app.state.login_limiter = LoginLimiter()

    errors.install(app)
    app.add_middleware(RequestContextMiddleware)

    for router in (health.router, auth.router, me.router, shifts.router, trips.router, admin_drivers.router):
        app.include_router(router)

    return app


configure_logging()
app = create_app()
