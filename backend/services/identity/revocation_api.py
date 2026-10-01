from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.dto import VersionRequest
from services.common.internal_dto import OperationQuery
from services.common.security import Principal, require_user_principal

from .revocation import Revocations

router = APIRouter(prefix="/internal/v1/browser")
Browser = Annotated[Principal, Depends(require_user_principal("identity:browser"))]


@router.post("/revoke")
async def revoke(command: VersionRequest, request: Request, principal: Browser):
    repository = Revocations(request.app.state.database, request.app.state.service_client)
    operation = await repository.accept(principal, command.expected_version)
    result = await repository.operation(principal.user_id, operation)
    return {
        "operation_id": str(operation),
        "state": result["state"],
        "poll_url": f"/api/v1/operations/{operation}",
    }


@router.post("/operation")
async def operation(command: OperationQuery, request: Request, principal: Browser):
    return await Revocations(
        request.app.state.database, request.app.state.service_client
    ).operation(principal.user_id, command.operation_id)
