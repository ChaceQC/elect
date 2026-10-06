"""查询读取与持久刷新入口，用户由服务身份确定。"""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from services.common.dates import today
from services.common.dto import DTO
from services.common.internal_dto import (
    BalanceObservation,
    BindingQuery,
    ConsumptionQuery,
    HistoryWindowQuery,
)
from services.common.security import Principal, require_user_principal
from services.common.sql import first

from .balance import accept_refresh, get_balance
from .consumption import consumption
from .history_jobs import accept_history
from .query_jobs import target
from .repository import RoomRepository

router = APIRouter(prefix="/internal/v1")
Browser = Annotated[Principal, Depends(require_user_principal("room:browser"))]


class RefreshCommand(BindingQuery):
    idempotency_key: str = Field(min_length=16, max_length=128)


class HistoryCommand(HistoryWindowQuery):
    idempotency_key: str = Field(min_length=16, max_length=128)


class OverviewQuery(DTO):
    binding_id: UUID | None = None


async def accepted(request, principal, operation):
    current = await RoomRepository(request.app.state.database).operation(
        principal.user_id, operation
    )
    return {
        "operation_id": str(operation),
        "state": current["state"],
        "poll_url": f"/api/v1/operations/{operation}",
    }


@router.post("/browser/balance")
async def balance(command: BindingQuery, request: Request, principal: Browser):
    return await get_balance(request.app.state.database, principal.user_id, command.binding_id)


@router.post("/browser/balance-refresh")
async def refresh(command: RefreshCommand, request: Request, principal: Browser):
    operation = await accept_refresh(
        request.app.state.database, principal.user_id, command.binding_id, command.idempotency_key
    )
    return await accepted(request, principal, operation)


@router.post("/browser/consumption")
async def get_consumption(command: ConsumptionQuery, request: Request, principal: Browser):
    return await consumption(request.app.state.database, principal.user_id, command)


@router.post("/browser/history-sync")
async def history_sync(command: HistoryCommand, request: Request, principal: Browser):
    operation = await accept_history(
        request.app.state.database,
        principal.user_id,
        command.binding_id,
        command,
        command.idempotency_key,
        principal.request_id,
    )
    return await accepted(request, principal, operation)


@router.post("/controls/query-target")
async def query_target(
    command: BindingQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("room:query"))],
):
    async with request.app.state.database.connect() as conn:
        row = await target(conn, principal.user_id, command.binding_id, active=True)
    return {"school_room_id": row["school_room_id"], "display_name": row["display_name"]}


@router.post("/controls/balance-observed")
async def balance_observed(
    command: BalanceObservation,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("room:balance-commit"))],
):
    from .balance_observations import apply_observation
    from .preference_store import lock_preference

    async with request.app.state.database.begin() as conn:
        await lock_preference(conn, principal.user_id)
        await target(conn, principal.user_id, command.binding_id, active=True)
        recorded = await apply_observation(
            conn, command.binding_id.bytes, command.amount,
            command.model_dump(exclude={"binding_id", "amount"}),
        )
    return {"recorded": recorded}


@router.post("/browser/overview")
async def overview(command: OverviewQuery, request: Request, principal: Browser):
    engine = request.app.state.database
    async with engine.connect() as conn:
        preference = await first(
            conn,
            "SELECT default_binding_id FROM room_preferences WHERE owner_user_id=:owner",
            owner=principal.user_id.bytes,
        )
    default = (
        UUID(bytes=preference["default_binding_id"])
        if preference and preference["default_binding_id"]
        else None
    )
    selected = command.binding_id or default
    repository = RoomRepository(engine)
    default_binding = await repository.get_binding(principal.user_id, default) if default else None
    if not selected:
        return {
            "viewing_binding_id": None,
            "default_binding": default_binding,
            "balance": None,
            "history": None,
        }
    await repository.get_binding(principal.user_id, selected)
    end = today()
    history = await consumption(
        engine,
        principal.user_id,
        ConsumptionQuery(binding_id=selected, start_date=end - timedelta(days=13), end_date=end),
    )
    return {
        "viewing_binding_id": selected,
        "default_binding": default_binding,
        "balance": await get_balance(engine, principal.user_id, selected),
        "history": history,
    }
