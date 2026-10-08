from fastapi import APIRouter, Depends, status
from psycopg_pool import ConnectionPool

from app.api.deps import get_pool
from app.core.constants import HEALTH_DB_TIMEOUT
from app.core.enums import ErrorCode
from app.core.errors import ApiError

router = APIRouter()


@router.get("/api/health")
def health(pool: ConnectionPool = Depends(get_pool)):
    """Liveness + database check, used by the Docker healthcheck."""
    try:
        with pool.connection(timeout=HEALTH_DB_TIMEOUT) as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        raise ApiError(
            ErrorCode.DB_UNAVAILABLE, "Database unavailable", status=status.HTTP_503_SERVICE_UNAVAILABLE
        ) from e
    return {"status": "ok"}
