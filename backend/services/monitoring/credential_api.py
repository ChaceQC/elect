from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.internal_dto import OperationQuery, RevokeBarrier, UpdateCredentialBarrier
from services.common.security import Principal, authorize_owner, require_user_principal

from .api import Credential
from .credentials import CredentialControls

router = APIRouter(prefix="/internal/v1/credentials")
Read = Annotated[Principal, Depends(require_user_principal("monitor:credential-read"))]


@router.post("/barrier")
async def barrier(command: OperationQuery, request: Request, principal: Read):
    return await CredentialControls(request.app.state.database).read(
        principal.user_id, command.operation_id
    )


@router.post("/prepare-update")
async def prepare(command: UpdateCredentialBarrier, request: Request, principal: Credential):
    authorize_owner(principal, command.owner_user_id)
    return await CredentialControls(request.app.state.database).prepare(command, revoke=False)


async def finish(command, request, principal, *, revoke=False, abort=False):
    authorize_owner(principal, command.owner_user_id)
    proof = await request.app.state.service_client.call(
        "school_adapter",
        "/credentials/control-view",
        "credential:control-read",
        principal.request_id,
        principal=principal,
    )
    controls = CredentialControls(request.app.state.database)
    if abort:
        return await controls.abort_update(command, proof)
    return await controls.commit(command, proof, revoke=revoke)


@router.post("/commit-update")
async def commit_update(command: UpdateCredentialBarrier, request: Request, principal: Credential):
    return await finish(command, request, principal)


@router.post("/abort-update")
async def abort_update(command: UpdateCredentialBarrier, request: Request, principal: Credential):
    return await finish(command, request, principal, abort=True)


@router.post("/commit-revoke")
async def commit_revoke(command: RevokeBarrier, request: Request, principal: Credential):
    return await finish(command, request, principal, revoke=True)
