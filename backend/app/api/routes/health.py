from fastapi import APIRouter, Depends
from psycopg_pool import ConnectionPool

from app.api.deps import get_pool
from app.core.errors import ApiError

router = APIRouter()


@router.get("/api/health")
def health(pool: ConnectionPool = Depends(get_pool)):
    """Liveness + database check, used by the Docker healthcheck."""
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise ApiError("db_unavailable", "Database unavailable", status=503)
    return {"status": "ok"}
