from fastapi import APIRouter, Depends, HTTPException, status
from psycopg_pool import ConnectionPool

from app.api.deps import get_pool

router = APIRouter()


@router.get("/api/health")
def health(pool: ConnectionPool = Depends(get_pool)):
    """Liveness + database check, used by the Docker healthcheck."""
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable")
    return {"status": "ok"}
