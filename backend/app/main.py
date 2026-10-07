from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool

from app.api.routes import auth, health, me, trips
from app.api.routes.admin import drivers as admin_drivers
from app.core.config import get_settings
from app.core.db import open_pool
from app.core.errors import DomainValidationError
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

    @app.exception_handler(DomainValidationError)
    async def domain_validation_error(request: Request, exc: DomainValidationError):
        # Reuse FastAPI's own 422 handler so both kinds of errors look the same
        from fastapi.exception_handlers import request_validation_exception_handler
        return await request_validation_exception_handler(
            request, RequestValidationError([exc.as_detail()]))

    for router in (health.router, auth.router, me.router, trips.router, admin_drivers.router):
        app.include_router(router)

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
