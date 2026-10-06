import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool

from .db import DEFAULT_DATABASE_URL, init_schema, open_pool
from .models import DayInfo, DaySummary, Trip, TripIn
from .seed import seed_demo
from .storage import TripConflict, TripStorage
from .summary import summarize

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_TRIPS = BASE_DIR / "data" / "trips.json"
STATIC_DIR = BASE_DIR / "static"


def get_storage(request: Request) -> TripStorage:
    return request.app.state.storage


def current_driver_id(storage: TripStorage = Depends(get_storage)) -> int:
    # TEMPORARY until authentication is added: everything belongs to the first driver.
    with storage.pool.connection() as conn:
        row = conn.execute("SELECT id FROM drivers ORDER BY id LIMIT 1").fetchone()
    if not row:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No drivers yet")
    return row["id"]


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
        app.state.storage = TripStorage(own_pool)
        try:
            yield
        finally:
            own_pool.close()

    app = FastAPI(title="Driver shift diary", lifespan=lifespan)
    if pool is not None:
        app.state.storage = TripStorage(pool)

    @app.get("/api/days", response_model=list[DayInfo])
    def list_days(storage: TripStorage = Depends(get_storage), driver_id: int = Depends(current_driver_id)):
        return storage.days(driver_id)

    @app.get("/api/trips", response_model=list[Trip])
    def list_trips(date: date, storage: TripStorage = Depends(get_storage),
                   driver_id: int = Depends(current_driver_id)):
        return storage.for_day(driver_id, date)

    @app.get("/api/summary", response_model=DaySummary)
    def day_summary(date: date, storage: TripStorage = Depends(get_storage),
                    driver_id: int = Depends(current_driver_id)):
        return summarize(storage.for_day(driver_id, date), date)

    @app.post("/api/trips", response_model=Trip, status_code=status.HTTP_201_CREATED)
    def add_trip(trip_in: TripIn, response: Response, storage: TripStorage = Depends(get_storage),
                 driver_id: int = Depends(current_driver_id)):
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
