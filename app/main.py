import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.staticfiles import StaticFiles

from .models import DayInfo, DaySummary, Trip, TripIn
from .storage import TripConflict, TripStorage
from .summary import day_index, summarize, trips_for_day

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA = BASE_DIR / "data" / "trips.json"
STATIC_DIR = BASE_DIR / "static"


def create_app(storage: TripStorage | None = None) -> FastAPI:
    storage = storage or TripStorage(Path(os.environ.get("TRIPS_FILE", DEFAULT_DATA)))
    app = FastAPI(title="Driver shift diary")

    @app.get("/api/days", response_model=list[DayInfo])
    def list_days():
        return day_index(storage.all())

    @app.get("/api/trips", response_model=list[Trip])
    def list_trips(date: date):
        return trips_for_day(storage.all(), date)

    @app.get("/api/summary", response_model=DaySummary)
    def day_summary(date: date):
        return summarize(storage.all(), date)

    @app.post("/api/trips", response_model=Trip, status_code=status.HTTP_201_CREATED)
    def add_trip(trip_in: TripIn, response: Response):
        try:
            trip, created = storage.add(trip_in.to_trip())
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
