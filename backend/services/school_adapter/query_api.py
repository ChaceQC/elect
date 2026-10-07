"""受内部身份保护的本人学校历史与监控余额读取。"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.dates import check_range
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import BindingQuery, HistoryExecutionQuery
from services.common.security import Principal, require_user_principal

from .application.meter_readings import collect_meter
from .infrastructure.history import records
from .infrastructure.transport import Deadline

router = APIRouter(prefix="/internal/v1/queries")


async def query_target(request, principal, binding, deadline=None):
    return await request.app.state.service_client.call(
        "room",
        "/controls/query-target",
        "room:query",
        principal.request_id,
        {"binding_id": str(binding)},
        principal=principal,
        budget=deadline.remaining() if deadline else None,
    )


@router.post("/history")
async def history(
    command: HistoryExecutionQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:history"))],
):
    check_range(command.start_date, command.end_date)
    if (command.end_date - command.start_date).days >= 7:
        raise ApiError(422, ErrorCode.INVALID_DATE_RANGE, "学校历史窗口最多7天")
    deadline = Deadline(command.budget_seconds)
    try:
        async with asyncio.timeout(deadline.remaining()):
            return await read_history(command, request, principal, deadline)
    except TimeoutError:
        raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "历史窗口执行超时", True) from None


async def read_history(command, request, principal, deadline):
    target = await query_target(request, principal, command.binding_id, deadline)
    value = await request.app.state.school_sessions.read(
        principal.user_id,
        principal.request_id,
        "/base/record/queryRecordByTime",
        {
            "buildId": target["school_room_id"],
            "startTimeStr": command.start_date.strftime("%Y%m%d"),
            "endTimeStr": command.end_date.strftime("%Y%m%d"),
        },
        budget=min(40, deadline.remaining()),
        read_timeout=20,
    )
    items = records(value, command.start_date, command.end_date)
    deadline.remaining()
    return {
        "items": items,
        "request_room_id": target["school_room_id"],
    }


@router.post("/collect")
async def collect(
    command: BindingQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:collect"))],
):
    budget = Deadline(85)
    target = await query_target(request, principal, command.binding_id)
    value = await request.app.state.school_sessions.read_bound(
        principal.user_id,
        principal.request_id,
        budget=budget.remaining(),
        read_timeout=15,
    )
    record = next(
        (row for row in value["items"] if row["room_id"] == target["school_room_id"]), None
    )
    try:
        async with asyncio.timeout(min(3, budget.remaining())):
            await request.app.state.service_client.call(
                "room",
                "/controls/balance-observed",
                "room:balance-commit",
                principal.request_id,
                {
                    "binding_id": str(command.binding_id),
                    "amount": record["balance"] if record else None,
                    **value["observation"],
                },
                principal=principal,
            )
    except (ApiError, TimeoutError):
        # 缓存更新失败不把本次已取得的余额作废；样本仍受monitor栅栏保护。
        pass
    if value["observation"]["error_code"]:
        raise ApiError(502, ErrorCode(value["observation"]["error_code"]),
                       "学校余额查询失败", True)
    if not record or record["balance"] is None:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "本人绑定未返回有效余额")
    meter = await collect_meter(
        request.app.state.school_sessions, principal.user_id, command.binding_id,
        target["school_room_id"], principal.request_id, budget,
    )
    return {"balance": record["balance"], **({"meter": meter} if meter else {})}
