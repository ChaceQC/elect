from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.internal_dto import CommitRetarget, PrepareRetarget, RevokeBarrier
from services.common.security import Principal, authorize_owner, require_user_principal

from .barriers import RetargetControls
from .configuration import MonitorConfiguration
from .credentials import CredentialControls
from .dto import MonitorPatch

router = APIRouter(prefix="/internal/v1")
Browser = Annotated[Principal, Depends(require_user_principal("monitor:browser"))]
Retarget = Annotated[Principal, Depends(require_user_principal("monitor:retarget"))]
Credential = Annotated[Principal, Depends(require_user_principal("monitor:credential"))]


def configuration(request):
    return MonitorConfiguration(request.app.state.database, request.app.state.email_crypto)


@router.post("/browser/monitor")
async def monitor(request: Request, principal: Browser):
    return await configuration(request).get(principal.user_id)


@router.post("/browser/monitor-config")
async def patch(command: MonitorPatch, request: Request, principal: Browser):
    return await configuration(request).patch(principal.user_id, command, principal.request_id)


@router.post("/monitor/prepare-retarget")
async def prepare(command: PrepareRetarget, request: Request, principal: Retarget):
    authorize_owner(principal, command.owner_user_id)
    return await RetargetControls(request.app.state.database).prepare(command)


async def finish_retarget(command, request, principal, compensate):
    authorize_owner(principal, command.owner_user_id)
    proof = await request.app.state.service_client.call(
        "room",
        "/controls/preference",
        "room:control",
        principal.request_id,
        {"operation_id": str(command.operation_id)},
        principal=principal,
    )
    return await RetargetControls(request.app.state.database).finish(
        command, proof, compensate=compensate
    )


@router.post("/monitor/commit-retarget")
async def commit(command: CommitRetarget, request: Request, principal: Retarget):
    return await finish_retarget(command, request, principal, False)


@router.post("/monitor/compensate-retarget")
async def compensate(command: PrepareRetarget, request: Request, principal: Retarget):
    return await finish_retarget(command, request, principal, True)


@router.post("/credentials/prepare-revoke")
async def prepare_revoke(command: RevokeBarrier, request: Request, principal: Credential):
    authorize_owner(principal, command.owner_user_id)
    return await CredentialControls(request.app.state.database).prepare(command, revoke=True)
