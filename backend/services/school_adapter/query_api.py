"""受内部身份保护的本人学校历史与监控余额读取。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.dates import check_range
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import BindingQuery, HistoryWindowQuery
from services.common.security import Principal, require_user_principal

from .infrastructure.history import records
from .infrastructure.rooms import bound_rooms

router = APIRouter(prefix="/internal/v1/queries")


async def query_target(request, principal, binding):
    return await request.app.state.service_client.call(
        "room",
        "/controls/query-target",
        "room:query",
        principal.request_id,
        {"binding_id": str(binding)},
        principal=principal,
    )


@router.post("/history")
async def history(
    command: HistoryWindowQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:history"))],
):
    check_range(command.start_date, command.end_date)
    if (command.end_date - command.start_date).days >= 7:
        raise ApiError(422, ErrorCode.INVALID_DATE_RANGE, "学校历史窗口最多7天")
    target = await query_target(request, principal, command.binding_id)
    value = await request.app.state.school_sessions.read(
        principal.user_id,
        principal.request_id,
        "/base/record/queryRecordByTime",
        {
            "buildId": target["school_room_id"],
            "startTimeStr": command.start_date.strftime("%Y%m%d"),
            "endTimeStr": command.end_date.strftime("%Y%m%d"),
        },
    )
    return {
        "items": records(value, command.start_date, command.end_date),
        "request_room_id": target["school_room_id"],
    }


@router.post("/collect")
async def collect(
    command: BindingQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:collect"))],
):
    target = await query_target(request, principal, command.binding_id)
    value = await request.app.state.school_sessions.read(
        principal.user_id,
        principal.request_id,
        "/base/roomUser/selectRoomListByUserId",
        {},
        include_user=True,
    )
    record = next(
        (row for row in bound_rooms(value) if row["room_id"] == target["school_room_id"]), None
    )
    if not record or record["balance"] is None:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "本人绑定未返回有效余额")
    return {"balance": record["balance"]}
