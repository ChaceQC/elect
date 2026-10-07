"""读取学校已支付记录，不依赖本系统订单或余额差推断。"""

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation

from services.common.dates import SHANGHAI, check_range
from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.transport import Deadline


def invalid():
    return ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校缴费明细结构异常")


def school_time(value, *, optional=False):
    if optional and value in (None, ""):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI)
    except (TypeError, ValueError):
        raise invalid() from None


def record(row, room_id):
    if (not isinstance(row, dict) or row.get("buildId") != room_id
            or row.get("payStatus") != "2" or row.get("orderType") != "0"
            or not isinstance(row.get("orderId"), str) or not row["orderId"]):
        raise invalid()
    try:
        amount = Decimal(row["payAmount"])
        if (not isinstance(row["payAmount"], str) or not amount.is_finite()
                or not 0 <= amount < Decimal("1000000000000")
                or amount != amount.quantize(Decimal("0.01"))):
            raise ValueError()
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise invalid() from None
    method = row.get("payMethod")
    if method is not None and not isinstance(method, str):
        raise invalid()
    return {"id": row["orderId"], "amount": format(amount, ".2f"),
            "created_at": school_time(row.get("createdTime")),
            "paid_at": school_time(row.get("payTime"), optional=True), "method": method}


def page(value, current, room_id):
    data = value.get("data") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or type(value.get("code")) is not int
            or value["code"] != 200 or not isinstance(data, dict)):
        raise invalid()
    rows, total, pages = data.get("records"), data.get("total"), data.get("pages")
    if (not isinstance(rows, list) or len(rows) > 10 or type(total) is not int or total < 0
            or type(pages) is not int or pages != (total + 9) // 10
            or type(data.get("current")) is not int or data["current"] != current
            or len(rows) != min(10, max(0, total - (current - 1) * 10))):
        raise invalid()
    return [record(row, room_id) for row in rows], total, pages


async def read(state, principal, command):
    check_range(command.start_date, command.end_date)
    deadline = Deadline(45)
    # 每次读取先由Room核实本人当前绑定；不相信浏览器学校标识。
    target = await state.service_client.call(
        "room", "/controls/query-target", "room:query", principal.request_id,
        {"binding_id": str(command.binding_id)}, principal=principal, budget=deadline.remaining(),
    )
    items, expected_total, complete = {}, None, False
    try:
        async with asyncio.timeout(deadline.remaining()):
            for current in range(1, 51):
                value = await state.school_sessions.read(
                    principal.user_id, principal.request_id, "/base/order/page",
                    {"buildId": target["school_room_id"],
                     "startTimeStr": command.start_date.isoformat(),
                     "endTimeStr": command.end_date.isoformat(), "current": current,
                     "size": 10, "pageTotal": expected_total if expected_total is not None else 100,
                     "orderType": 0, "payStatus": 2},
                    budget=min(20, deadline.remaining()), read_timeout=15,
                )
                rows, total, pages = page(value, current, target["school_room_id"])
                if expected_total is not None and total != expected_total:
                    break
                expected_total = total
                if (any(row["id"] in items for row in rows)
                        or len({r["id"] for r in rows}) != len(rows)):
                    break
                items.update((row["id"], row) for row in rows)
                if current >= pages:
                    complete = len(items) == total
                    break
    except (TimeoutError, ApiError) as error:
        # 不把半途失败的分页当成完整总额；首屏失败仍走标准错误/退避响应。
        if isinstance(error, ApiError) and error.status in {401, 403, 409, 429}:
            raise
        if expected_total is None:
            if isinstance(error, TimeoutError):
                raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "学校缴费查询超时", True) from None
            raise
    amount = format(sum((Decimal(row["amount"]) for row in items.values()), Decimal(0)), ".2f")
    ordered = sorted(items.values(),
                     key=lambda row: (row["paid_at"] or row["created_at"], row["id"]), reverse=True)
    return {"items": ordered,
            "total": expected_total or 0, "known_amount": amount,
            "total_amount": amount if complete else None, "complete": complete}
