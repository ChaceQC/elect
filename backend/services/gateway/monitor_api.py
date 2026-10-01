from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from services.common.browser_security import require_browser_write
from services.common.dto import VersionRequest
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


@router.post("/monitor/runs", status_code=202)
async def create_run(
    request: Request, idempotency_key: Annotated[str, Header(min_length=16, max_length=128)]
):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await request.app.state.service_client.call(
        "monitoring",
        "/browser/runs",
        "monitor:browser",
        principal.request_id,
        {"idempotency_key": idempotency_key},
        principal=principal,
    )
    return success(request, value, status=202)


@router.get("/monitor/runs/{id}")
async def get_run(id: UUID, request: Request):
    principal, _ = await session(request)
    value = await request.app.state.service_client.call(
        "monitoring",
        "/browser/run",
        "monitor:browser",
        principal.request_id,
        {"run_id": str(id)},
        principal=principal,
    )
    return success(request, value)


@router.post("/monitor/runs/{id}/cancel")
async def cancel_run(id: UUID, command: VersionRequest, request: Request):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await request.app.state.service_client.call(
        "monitoring",
        "/browser/cancel",
        "monitor:browser",
        principal.request_id,
        {"run_id": str(id), **command.model_dump()},
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
