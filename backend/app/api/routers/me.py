from typing import Annotated, Any

from fastapi import APIRouter, Body, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import AccountServiceDep, CurrentPrincipal, DriverId
from app.core.constants import DRIVER_SELF_EDITABLE
from app.core.enums import ErrorCode
from app.core.errors import ApiError
from app.domain.models import AccountProfile
from app.schemas.accounts import Profile, SelfProfileUpdate

router = APIRouter(prefix="/api/me", tags=["profile"])


@router.get("", response_model=Profile)
async def me(accounts: AccountServiceDep, principal: CurrentPrincipal) -> AccountProfile:
    return await accounts.profile(principal.id)


@router.patch("", response_model=Profile)
async def update_me(
    body: Annotated[dict[str, Any], Body()], accounts: AccountServiceDep, driver_id: DriverId
) -> AccountProfile:
    # Explicit 403 rather than silently ignoring fields the driver may not change
    if forbidden := sorted(set(body) - DRIVER_SELF_EDITABLE):
        raise ApiError(
            ErrorCode.ADMIN_MANAGED_FIELDS,
            "These fields are managed by the admin",
            status=status.HTTP_403_FORBIDDEN,
            fields=forbidden,
        )
    try:
        changes = SelfProfileUpdate.model_validate(body)
    except ValidationError as e:
        # Validated by hand (the body is a plain dict), so report it as FastAPI would
        raise RequestValidationError(
            [{**err, "loc": ("body", *err["loc"])} for err in e.errors(include_url=False)]
        ) from e
    return await accounts.set_timezone(driver_id, changes.default_tz)
