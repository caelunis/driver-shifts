import logging

from fastapi import APIRouter, status

from app.api.deps import DbDep
from app.core.constants import HEALTH_DB_TIMEOUT
from app.core.enums import ErrorCode
from app.core.errors import ApiError
from app.schemas.errors import ErrorBody

# Outside the versioned API: Docker and load balancers poll it, whatever the API version
router = APIRouter(tags=["service"])
log = logging.getLogger(__name__)


@router.get(
    "/api/health",
    summary="Service and database are up",
    responses={503: {"model": ErrorBody, "description": "The database is unreachable"}},
)
async def health(db: DbDep) -> dict[str, str]:
    """Used by the Docker healthcheck. No session needed."""
    try:
        await db.ping(HEALTH_DB_TIMEOUT)
    except Exception as e:
        log.warning("db_unavailable", exc_info=True)
        raise ApiError(
            ErrorCode.DB_UNAVAILABLE, "Database unavailable", status=status.HTTP_503_SERVICE_UNAVAILABLE
        ) from e
    return {"status": "ok"}
