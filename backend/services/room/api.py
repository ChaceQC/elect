from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from services.common.dto import DTO
from services.common.internal_dto import OperationQuery, RoomQuery
from services.common.security import Principal, require_user_principal

from .dto import Candidates
from .repository import RoomRepository

router = APIRouter(prefix="/internal/v1/browser")
Browser = Annotated[Principal, Depends(require_user_principal("room:browser"))]


class SyncCommand(DTO):
    idempotency_key: str = Field(min_length=16, max_length=128)


@router.post("/bindings")
async def bindings(command: RoomQuery, request: Request, principal: Browser):
    return await RoomRepository(request.app.state.database).list(
        principal.user_id, command.q, command.page, command.page_size
    )


@router.post("/sync")
async def sync(command: SyncCommand, request: Request, principal: Browser):
    operation = await RoomRepository(request.app.state.database).accept_sync(
        principal.user_id, command.idempotency_key
    )
    current = await RoomRepository(request.app.state.database).operation(
        principal.user_id, operation
    )
    return {
        "operation_id": str(operation),
        "state": current["state"],
        "poll_url": f"/api/v1/operations/{operation}",
    }


@router.post("/operation")
async def operation(command: OperationQuery, request: Request, principal: Browser):
    return await RoomRepository(request.app.state.database).operation(
        principal.user_id, command.operation_id
    )


@router.post("/candidates")
async def candidates(command: RoomQuery, request: Request, principal: Browser):
    value = await request.app.state.service_client.call(
        "school_adapter",
        "/rooms/candidates",
        "school:rooms",
        principal.request_id,
        command.model_dump(),
        principal=principal,
    )
    bound = await RoomRepository(request.app.state.database).bound_school_ids(principal.user_id)
    for item in value["items"]:
        item["already_bound"] = item["room_id"] in bound
    return Candidates.model_validate(value)
