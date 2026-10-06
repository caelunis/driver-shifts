import json
import os
import tempfile
import threading
from pathlib import Path

from .models import Trip


class TripConflict(Exception):
    """A trip with this id already exists, but with different data."""

    def __init__(self, existing: Trip):
        self.existing = existing


class TripStorage:
    """Trip storage backed by a JSON file.

    All operations run under a lock; writes are atomic (temp file + replace),
    so a crash mid-write never leaves a half-written file behind.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> list[Trip]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [Trip(**item) for item in json.load(f)]

    def _write(self, trips: list[Trip]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [t.model_dump(mode="json") for t in trips]
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise

    def all(self) -> list[Trip]:
        with self._lock:
            return self._read()

    def add(self, trip: Trip) -> tuple[Trip, bool]:
        """Idempotent insert. Returns (trip, created)."""
        with self._lock:
            trips = self._read()
            for existing in trips:
                if existing.id == trip.id:
                    if existing.same_content(trip):
                        return existing, False
                    raise TripConflict(existing)
            trips.append(trip)
            self._write(trips)
            return trip, True
