"""本人默认与绑定写操作的浏览器入口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from services.common.browser_security import require_browser_write
from services.common.internal_dto import RoomFilterQuery
from services.room.dto import BindRequest, DefaultRequest

from .api import session, success

router = APIRouter(prefix="/api/v1")


@router.get("/room-bindings/{id}")
async def binding(id: UUID, request: Request):
    principal, _ = await session(request)
    value = await request.app.state.service_client.call(
        "room",
        "/browser/binding",
        "room:browser",
        principal.request_id,
        {"binding_id": str(id)},
        principal=principal,
    )
    return success(request, value)


@router.put("/room-preferences/default")
async def set_default(command: DefaultRequest, request: Request):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await request.app.state.service_client.call(
        "room",
        "/browser/default",
        "room:browser",
        principal.request_id,
        command.model_dump(mode="json"),
        principal=principal,
    )
    return success(request, value, status=202 if "operation_id" in value else 200)


async def filters(request, level, building_id=None, floor=None):
    principal, _ = await session(request)
    command = RoomFilterQuery(level=level, building_id=building_id, floor=floor)
    value = await request.app.state.service_client.call(
        "room",
        "/browser/filters",
        "room:browser",
        principal.request_id,
        command.model_dump(mode="json"),
        principal=principal,
    )
    return success(request, value)


@router.get("/room-candidates/buildings")
async def buildings(request: Request):
    return await filters(request, "buildings")


@router.get("/room-candidates/floors")
async def floors(request: Request, building_id: str = Query(min_length=1, max_length=128)):
    return await filters(request, "floors", building_id)


@router.get("/room-candidates/rooms")
async def rooms(
    request: Request,
    building_id: str = Query(min_length=1, max_length=128),
    floor: str = Query(min_length=1, max_length=128),
):
    return await filters(request, "rooms", building_id, floor)


@router.post("/room-bindings", status_code=202)
async def bind(
    command: BindRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=16, max_length=128)],
):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await request.app.state.service_client.call(
        "room",
        "/browser/bind",
        "room:browser",
        principal.request_id,
        {**command.model_dump(), "idempotency_key": idempotency_key},
        principal=principal,
    )
    return success(request, value, status=202)
