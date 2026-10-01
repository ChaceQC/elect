from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.internal_dto import AlertSlotQuery, AuthorizeSend
from services.common.security import Principal, authorize_owner, require_user_principal

from .alert_snapshot import snapshot
from .permits import authorize

router = APIRouter(prefix="/internal/v1/alert-slots")


@router.post("/snapshot")
async def alert_snapshot(
    command: AlertSlotQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("monitor:alert-read"))],
):
    authorize_owner(principal, command.owner_user_id)
    return await snapshot(request.app, command, principal)


@router.post("/authorize-send")
async def authorize_send(
    command: AuthorizeSend,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("monitor:authorize-send"))],
):
    authorize_owner(principal, command.owner_user_id)
    return await authorize(request.app.state.database, command)
