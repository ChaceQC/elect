"""总览组件与已授权日消费合并；不跨库读取原始记录。"""

import asyncio
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from services.common.browser_security import require_browser_write
from services.common.dates import check_range, today
from services.common.http import ApiError
from services.room.dto import HistoryRequest, Overview

from .api import SESSION_COOKIE, session, success
from .consumption import with_monitoring
from .cookies import get_cookie

router = APIRouter(prefix="/api/v1")
Key = Annotated[str, Header(min_length=16, max_length=128)]


async def room_call(request, principal, path, payload):
    return await request.app.state.service_client.call(
        "room",
        "/browser/" + path,
        "room:browser",
        principal.request_id,
        payload,
        principal=principal,
    )


@router.get("/room-bindings/{id}/balance")
async def balance(id: UUID, request: Request):
    principal, _ = await session(request)
    return success(request, await room_call(request, principal, "balance", {"binding_id": str(id)}))


@router.post("/room-bindings/{id}/balance-refresh", status_code=202)
async def refresh(id: UUID, request: Request, idempotency_key: Key):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    return success(
        request,
        await room_call(
            request,
            principal,
            "balance-refresh",
            {"binding_id": str(id), "idempotency_key": idempotency_key},
        ),
        status=202,
    )


@router.get("/room-bindings/{id}/consumption")
async def consumption(
    id: UUID,
    request: Request,
    start_date: date | None = None,
    end_date: date | None = None,
    granularity: Literal["day", "week", "month"] = "day",
):
    principal, _ = await session(request)
    end = end_date or today()
    start = start_date or end - timedelta(days=29)
    check_range(start, end)
    value = await room_call(
        request,
        principal,
        "consumption",
        {
            "binding_id": str(id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "granularity": "day",
        },
    )
    return success(request, await with_monitoring(request, principal, value, granularity))


@router.post("/room-bindings/{id}/history-sync", status_code=202)
async def history_sync(id: UUID, command: HistoryRequest, request: Request, idempotency_key: Key):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await room_call(
        request,
        principal,
        "history-sync",
        {
            "binding_id": str(id),
            **command.model_dump(mode="json"),
            "idempotency_key": idempotency_key,
        },
    )
    return success(request, value, status=202)


@router.get("/room-bindings/{id}/monitor-samples")
async def samples(
    id: UUID,
    request: Request,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    snapshot_token: str | None = Query(None, min_length=16, max_length=128),
):
    principal, _ = await session(request)
    end = end_date or today()
    start = start_date or end - timedelta(days=29)
    check_range(start, end)
    # 每次分页也核对本人绑定；关闭监控/归档不删除其历史归属。
    await room_call(request, principal, "balance", {"binding_id": str(id)})
    value = await request.app.state.service_client.call(
        "monitoring",
        "/browser/samples",
        "monitor:browser",
        principal.request_id,
        {
            "binding_id": str(id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "page": page,
            "page_size": page_size,
            "snapshot_token": snapshot_token,
        },
        principal=principal,
    )
    return success(request, value)


@router.get("/overview")
async def overview(request: Request, binding_id: UUID | None = None):
    principal, _ = await session(request)
    client = request.app.state.service_client
    room, me, monitor = await asyncio.gather(
        room_call(
            request, principal, "overview", {"binding_id": str(binding_id) if binding_id else None}
        ),
        client.call(
            "identity",
            "/browser/me",
            "identity:browser",
            principal.request_id,
            {"session_token": get_cookie(request, SESSION_COOKIE)},
            principal=principal,
        ),
        client.call(
            "monitoring",
            "/browser/monitor",
            "monitor:browser",
            principal.request_id,
            principal=principal,
        ),
        return_exceptions=True,
    )
    if isinstance(room, ApiError) and room.status == 404:
        raise room
    if isinstance(room, Exception):
        room = None
    if isinstance(me, Exception):
        me = None
    if isinstance(monitor, Exception):
        monitor = None
    history = room["history"] if room else None
    if history:
        history = await with_monitoring(request, principal, history, "day")
    balance = room["balance"] if room else None
    result = Overview(
        viewing_binding_id=room["viewing_binding_id"] if room else binding_id,
        profile={
            "student_id": me["student_id"],
            "default_binding": room["default_binding"] if room else None,
            "alert_email": monitor["config"]["email"] if monitor else None,
        }
        if me
        else None,
        balance=balance,
        summary={
            "yesterday_amount": None,
            "last_14_days_amount": history["summary"]["amount"],
            **{key: history["summary"][key] for key in ("known_days", "expected_days", "complete")},
        }
        if history
        else None,
        daily_consumption=history,
        monitor={
            "enabled": monitor["config"]["enabled"],
            "state": monitor["state"],
            "health": monitor["health"],
            "interval_minutes": monitor["config"]["interval_minutes"],
        }
        if monitor
        else None,
        component_status={
            "profile": "ready" if me and room else "partial" if me else "failed",
            "balance": "failed"
            if not room
            else "empty"
            if not balance or balance["amount"] is None
            else "stale"
            if balance["stale"]
            else "ready",
            "history": history["sync_status"] if history else "empty" if room else "failed",
            "monitor": "ready" if monitor else "failed",
        },
    )
    return success(request, result.model_dump(mode="json"))
