import logging

from fastapi import APIRouter, status

from app.api.deps import DbDep
from app.core.constants import HEALTH_DB_TIMEOUT
from app.core.enums import ErrorCode
from app.core.errors import ApiError

router = APIRouter(tags=["service"])
log = logging.getLogger(__name__)


@router.get("/api/health")
async def health(db: DbDep) -> dict[str, str]:
    """Liveness + database check, used by the Docker healthcheck."""
    try:
        await db.ping(HEALTH_DB_TIMEOUT)
    except Exception as e:
        log.warning("db_unavailable", exc_info=True)
        raise ApiError(
            ErrorCode.DB_UNAVAILABLE, "Database unavailable", status=status.HTTP_503_SERVICE_UNAVAILABLE
        ) from e
    return {"status": "ok"}
