"""本人默认与绑定写操作的浏览器入口。"""

from fastapi import APIRouter, Request

from services.common.browser_security import require_browser_write
from services.room.dto import DefaultRequest

from .api import session, success

router = APIRouter(prefix="/api/v1")


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
