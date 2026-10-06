import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Body, Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from psycopg_pool import ConnectionPool

from . import accounts, admin
from .commission import resolve_commission
from .db import DEFAULT_DATABASE_URL, init_schema, open_pool
from .deps import (
    SESSION_COOKIE, current_account, get_storage, require_driver, require_json, set_session_cookie,
)
from .models import DayInfo, DaySummary, LoginIn, Profile, SelfProfileUpdate, Trip, TripIn
from .security import LoginLimiter
from .seed import ensure_admin, seed_demo
from .storage import TripConflict, TripStorage
from .summary import summarize

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_TRIPS = BASE_DIR / "data" / "trips.json"
STATIC_DIR = BASE_DIR / "static"

# Profile fields a driver may change; everything else is managed by the admin
DRIVER_EDITABLE = {"default_tz"}


def create_app(pool: ConnectionPool | None = None) -> FastAPI:
    """Pass a pool in tests; otherwise the app connects to DATABASE_URL on startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pool is not None:
            yield
            return
        own_pool = open_pool(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        init_schema(own_pool)
        if os.environ.get("SEED_DEMO") == "1":
            seed_demo(own_pool, DEMO_TRIPS)
        if os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD"):
            ensure_admin(own_pool, os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])
        app.state.storage = TripStorage(own_pool)
        try:
            yield
        finally:
            own_pool.close()

    app = FastAPI(title="Driver shift diary", lifespan=lifespan)
    if pool is not None:
        app.state.storage = TripStorage(pool)
    app.state.login_limiter = LoginLimiter()

    @app.get("/api/health")
    def health(storage: TripStorage = Depends(get_storage)):
        """Liveness + database check, used by the Docker healthcheck."""
        try:
            with storage.pool.connection(timeout=2) as conn:
                conn.execute("SELECT 1")
        except Exception:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable")
        return {"status": "ok"}

    # --- session ---

    @app.post("/api/auth/login", response_model=Profile)
    def login(data: LoginIn, request: Request, response: Response,
              storage: TripStorage = Depends(get_storage)):
        limiter: LoginLimiter = request.app.state.login_limiter
        key = data.email.lower()
        if wait := limiter.retry_after(key):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts",
                                headers={"Retry-After": str(wait)})
        account_id = accounts.authenticate(storage.pool, data.email, data.password)
        if account_id is None:
            limiter.failure(key)
            # Same answer for unknown email and wrong password
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        limiter.success(key)
        set_session_cookie(response, accounts.create_session(storage.pool, account_id))
        return accounts.get_profile(storage.pool, account_id)

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT,
              dependencies=[Depends(require_json)])
    def logout(response: Response, session: str | None = Cookie(default=None),
               storage: TripStorage = Depends(get_storage)):
        if session:
            accounts.delete_session(storage.pool, session)
        response.delete_cookie(SESSION_COOKIE, path="/")

    @app.get("/api/me", response_model=Profile)
    def me(storage: TripStorage = Depends(get_storage), account: dict = Depends(current_account)):
        return accounts.get_profile(storage.pool, account["id"])

    @app.patch("/api/me", response_model=Profile)
    def update_me(body: dict = Body(...), storage: TripStorage = Depends(get_storage),
                  driver_id: int = Depends(require_driver)):
        # Explicit 403 rather than silently ignoring fields the driver may not change
        if forbidden := sorted(set(body) - DRIVER_EDITABLE):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                {"message": "These fields are managed by the admin",
                                 "fields": forbidden})
        try:
            changes = SelfProfileUpdate.model_validate(body)
        except ValidationError as e:
            # Validated by hand (the body is a plain dict), so report it as FastAPI would
            raise RequestValidationError(
                [{**err, "loc": ("body", *err["loc"])} for err in e.errors(include_url=False)]
            )
        return accounts.set_timezone(storage.pool, driver_id, changes.default_tz)

    # --- the driver's own trips ---

    @app.get("/api/days", response_model=list[DayInfo])
    def list_days(storage: TripStorage = Depends(get_storage),
                  driver_id: int = Depends(require_driver)):
        return storage.days(driver_id)

    @app.get("/api/trips", response_model=list[Trip])
    def list_trips(date: date, storage: TripStorage = Depends(get_storage),
                   driver_id: int = Depends(require_driver)):
        return storage.for_day(driver_id, date)

    @app.get("/api/summary", response_model=DaySummary)
    def day_summary(date: date, storage: TripStorage = Depends(get_storage),
                    driver_id: int = Depends(require_driver)):
        return summarize(storage.for_day(driver_id, date), date)

    @app.post("/api/trips", response_model=Trip, status_code=status.HTTP_201_CREATED)
    def add_trip(trip_in: TripIn, response: Response, storage: TripStorage = Depends(get_storage),
                 driver_id: int = Depends(require_driver)):
        pct = accounts.get_profile(storage.pool, driver_id).default_commission_pct
        trip_in = resolve_commission(trip_in, pct)
        try:
            trip, created = storage.add(driver_id, trip_in.to_trip())
        except TripConflict as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"Trip with id={e.existing.id} already exists with different data",
                    "existing": e.existing.model_dump(mode="json"),
                },
            )
        if not created:
            response.status_code = status.HTTP_200_OK
        return trip

    app.include_router(admin.router)

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
