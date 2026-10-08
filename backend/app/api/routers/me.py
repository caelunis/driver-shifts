from typing import Annotated, Any

from fastapi import APIRouter, Body, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import AccountServiceDep, Authenticated, CurrentPrincipal, DriverId
from app.core.constants import API_V1, DRIVER_SELF_EDITABLE
from app.core.enums import ErrorCode
from app.core.errors import ApiError
from app.domain.models import AccountProfile
from app.schemas.accounts import Profile, SelfProfileUpdate
from app.schemas.errors import responses

router = APIRouter(
    prefix=f"{API_V1}/me", tags=["profile"], dependencies=[Authenticated], responses=responses(401, 429)
)


@router.get("", response_model=Profile, summary="Who am I")
async def me(accounts: AccountServiceDep, principal: CurrentPrincipal) -> AccountProfile:
    """The logged-in account; driver fields are null for the admin."""
    return await accounts.profile(principal.id)


@router.patch(
    "",
    response_model=Profile,
    summary="Change my timezone",
    responses=responses(403, 422),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    # Inline: the handler takes a plain dict (to answer 403 for fields the
                    # driver may not change), so the model is not registered as a component
                    "schema": SelfProfileUpdate.model_json_schema(),
                    "example": {"timezone": "Asia/Almaty"},
                }
            },
        }
    },
)
async def update_me(
    body: Annotated[dict[str, Any], Body()], accounts: AccountServiceDep, driver_id: DriverId
) -> AccountProfile:
    """A driver changes only `timezone`; any other field is **403 admin_managed_fields**."""
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
    return await accounts.set_timezone(driver_id, changes.timezone)
