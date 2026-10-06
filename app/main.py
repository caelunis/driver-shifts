import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool

from . import accounts
from .db import DEFAULT_DATABASE_URL, init_schema, open_pool
from .models import DayInfo, DaySummary, LoginIn, Profile, ProfileUpdate, Trip, TripIn
from .security import LoginLimiter
from .seed import ensure_admin, seed_demo
from .storage import TripConflict, TripStorage
from .summary import summarize

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_TRIPS = BASE_DIR / "data" / "trips.json"
STATIC_DIR = BASE_DIR / "static"

SESSION_COOKIE = "session"
# Set COOKIE_SECURE=1 behind HTTPS; plain-HTTP localhost needs it off
COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"


def get_storage(request: Request) -> TripStorage:
    return request.app.state.storage


def session_driver_id(request: Request, session: str | None = Cookie(default=None)) -> int:
    driver_id = accounts.driver_by_session(request.app.state.storage.pool, session) if session else None
    if driver_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return driver_id


def require_json(request: Request) -> None:
    """CSRF guard for body-less state-changing requests.

    A cross-site HTML form cannot send Content-Type: application/json, and with
    SameSite=Lax the cookie is not attached to cross-site fetches either.
    Endpoints with a JSON body get this check from FastAPI's body parsing.
    """
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Expected application/json")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(accounts.SESSION_TTL.total_seconds()),
        httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/",
    )


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

    # --- accounts ---

    @app.post("/api/auth/login", response_model=Profile)
    def login(data: LoginIn, request: Request, response: Response,
              storage: TripStorage = Depends(get_storage)):
        limiter: LoginLimiter = request.app.state.login_limiter
        key = data.email.lower()
        if wait := limiter.retry_after(key):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts",
                                headers={"Retry-After": str(wait)})
        driver_id = accounts.authenticate(storage.pool, data.email, data.password)
        if driver_id is None:
            limiter.failure(key)
            # Same answer for unknown email and wrong password
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        limiter.success(key)
        set_session_cookie(response, accounts.create_session(storage.pool, driver_id))
        return accounts.get_profile(storage.pool, driver_id)

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT,
              dependencies=[Depends(require_json)])
    def logout(response: Response, session: str | None = Cookie(default=None),
               storage: TripStorage = Depends(get_storage)):
        if session:
            accounts.delete_session(storage.pool, session)
        response.delete_cookie(SESSION_COOKIE, path="/")

    @app.get("/api/me", response_model=Profile)
    def me(storage: TripStorage = Depends(get_storage), driver_id: int = Depends(session_driver_id)):
        return accounts.get_profile(storage.pool, driver_id)

    @app.patch("/api/me", response_model=Profile)
    def update_me(changes: ProfileUpdate, storage: TripStorage = Depends(get_storage),
                  driver_id: int = Depends(session_driver_id)):
        return accounts.update_profile(storage.pool, driver_id, changes.model_dump(exclude_unset=True))

    # --- trips ---

    @app.get("/api/days", response_model=list[DayInfo])
    def list_days(storage: TripStorage = Depends(get_storage), driver_id: int = Depends(session_driver_id)):
        return storage.days(driver_id)

    @app.get("/api/trips", response_model=list[Trip])
    def list_trips(date: date, storage: TripStorage = Depends(get_storage),
                   driver_id: int = Depends(session_driver_id)):
        return storage.for_day(driver_id, date)

    @app.get("/api/summary", response_model=DaySummary)
    def day_summary(date: date, storage: TripStorage = Depends(get_storage),
                    driver_id: int = Depends(session_driver_id)):
        return summarize(storage.for_day(driver_id, date), date)

    @app.post("/api/trips", response_model=Trip, status_code=status.HTTP_201_CREATED)
    def add_trip(trip_in: TripIn, response: Response, storage: TripStorage = Depends(get_storage),
                 driver_id: int = Depends(session_driver_id)):
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

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
