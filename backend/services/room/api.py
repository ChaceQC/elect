from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from services.common.dto import DTO
from services.common.internal_dto import BindingQuery, OperationQuery, RoomFilterQuery, RoomQuery
from services.common.security import Principal, require_user_principal

from .defaults import accept_default
from .dto import BindRequest, Candidates, DefaultRequest
from .repository import RoomRepository

router = APIRouter(prefix="/internal/v1/browser")
Browser = Annotated[Principal, Depends(require_user_principal("room:browser"))]


class SyncCommand(DTO):
    idempotency_key: str = Field(min_length=16, max_length=128)


class BindCommand(BindRequest, SyncCommand):
    pass


class RemoveCommand(BindingQuery, SyncCommand):
    pass


@router.post("/bindings")
async def bindings(command: RoomQuery, request: Request, principal: Browser):
    return await RoomRepository(request.app.state.database).list(
        principal.user_id, command.q, command.page, command.page_size
    )


@router.post("/binding")
async def binding(command: BindingQuery, request: Request, principal: Browser):
    return await RoomRepository(request.app.state.database).get_binding(
        principal.user_id, command.binding_id
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


@router.post("/default")
async def set_default(command: DefaultRequest, request: Request, principal: Browser):
    async with request.app.state.database.begin() as conn:
        operation = await accept_default(
            conn,
            principal.user_id,
            command.binding_id,
            command.expected_version,
            principal.request_id,
        )
    if operation is None:
        return {
            "default_binding_id": str(command.binding_id),
            "preference_version": command.expected_version,
            "state": "ready",
        }
    current = await RoomRepository(request.app.state.database).operation(
        principal.user_id, operation
    )
    return {
        "operation_id": str(operation),
        "state": current["state"],
        "poll_url": f"/api/v1/operations/{operation}",
    }


@router.post("/filters")
async def filters(command: RoomFilterQuery, request: Request, principal: Browser):
    return await request.app.state.service_client.call(
        "school_adapter",
        "/rooms/filters",
        "school:rooms",
        principal.request_id,
        command.model_dump(mode="json"),
        principal=principal,
    )


@router.post("/bind")
async def bind(command: BindCommand, request: Request, principal: Browser):
    from .bindings import accept

    operation = await accept(
        request.app.state, principal, command.candidate_id, command.idempotency_key
    )
    current = await RoomRepository(request.app.state.database).operation(
        principal.user_id, operation
    )
    return {
        "operation_id": str(operation),
        "state": current["state"],
        "poll_url": f"/api/v1/operations/{operation}",
    }


@router.post("/unbind")
async def unbind(command: RemoveCommand, request: Request, principal: Browser):
    from .removals import accept

    operation = await accept(
        request.app.state, principal, command.binding_id, command.idempotency_key
    )
    current = await RoomRepository(request.app.state.database).operation(
        principal.user_id, operation
    )
    return {
        "operation_id": str(operation),
        "state": current["state"],
        "poll_url": f"/api/v1/operations/{operation}",
    }
