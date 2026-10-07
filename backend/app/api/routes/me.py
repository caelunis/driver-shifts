from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.api.deps import current_account, get_pool, require_driver
from app.schemas.accounts import Profile, SelfProfileUpdate
from app.services import accounts

router = APIRouter(prefix="/api/me")

# Profile fields a driver may change; everything else is managed by the admin
DRIVER_EDITABLE = {"default_tz"}


@router.get("", response_model=Profile)
def me(pool: ConnectionPool = Depends(get_pool), account: dict = Depends(current_account)):
    return accounts.get_profile(pool, account["id"])


@router.patch("", response_model=Profile)
def update_me(body: dict = Body(...), pool: ConnectionPool = Depends(get_pool),
              driver_id: int = Depends(require_driver)):
    # Explicit 403 rather than silently ignoring fields the driver may not change
    if forbidden := sorted(set(body) - DRIVER_EDITABLE):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            {"message": "These fields are managed by the admin", "fields": forbidden})
    try:
        changes = SelfProfileUpdate.model_validate(body)
    except ValidationError as e:
        # Validated by hand (the body is a plain dict), so report it as FastAPI would
        raise RequestValidationError(
            [{**err, "loc": ("body", *err["loc"])} for err in e.errors(include_url=False)]
        )
    return accounts.set_timezone(pool, driver_id, changes.default_tz)
