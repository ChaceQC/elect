from uuid import UUID

from fastapi import APIRouter, Request

from services.common.browser_security import require_browser_write
from services.monitoring.dto import MonitorPatch

from .api import session, success

router = APIRouter(prefix="/api/v1")


@router.get("/monitor")
async def monitor(request: Request):
    principal, _ = await session(request)
    value = await request.app.state.service_client.call(
        "monitoring",
        "/browser/monitor",
        "monitor:browser",
        UUID(request.state.request_id),
        principal=principal,
    )
    return success(request, value)


@router.patch("/monitor")
async def patch_monitor(command: MonitorPatch, request: Request):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await request.app.state.service_client.call(
        "monitoring",
        "/browser/monitor-config",
        "monitor:browser",
        UUID(request.state.request_id),
        command.model_dump(mode="json", exclude_unset=True),
        principal=principal,
    )
    return success(request, value)
