"""D04已支付订单精确回查；不以同金额、时间接近或列表缺席推断结果。"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from services.common.dates import today
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import aware

from ..infrastructure.payment_protocol import original_order_paid
from ..infrastructure.payment_transport import PaymentTransport

FIELDS = (
    "orderId", "tradeOrderNo", "buildId", "orderAmount", "payAmount",
    "orderType", "payMethod", "payStatus", "userId", "createdTime",
)


def order_page(value, current):
    data = value.get("data")
    if type(value.get("code")) is not int or value["code"] != 200 or not isinstance(data, dict):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校订单列表无有效结果")
    rows, pages = data.get("records"), data.get("pages")
    if (not isinstance(rows, list) or len(rows) > 10 or type(pages) is not int
            or pages < 0 or type(data.get("current")) is not int or data["current"] != current
            or (pages == 0 and rows) or (pages > 0 and not rows)):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校订单分页结构异常")
    if any(not isinstance(row, dict) for row in rows):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校订单明细结构异常")
    return [{key: row.get(key) for key in FIELDS} for row in rows], pages


def same_order(row, payload):
    # 两类标识都只允许非空字符串的完整相等；禁止子串/金额/时间关联。
    prepay, sdgl = payload.get("prepay_id"), payload.get("sdgl_order_id")
    return bool(
        (isinstance(sdgl, str) and sdgl and row.get("orderId") == sdgl)
        or (isinstance(prepay, str) and prepay
            and prepay in (row.get("orderId"), row.get("tradeOrderNo")))
    )


def confirms_paid(row, payload):
    if (row.get("buildId") != payload["school_room_id"] or row.get("payStatus") != "2"
            or row.get("orderType") != "0" or row.get("payMethod") != "1"):
        return False
    try:
        amount = Decimal(payload["amount"])
        return all(
            type(row.get(key)) is str and Decimal(row[key]).is_finite()
            and Decimal(row[key]) == amount
            for key in ("orderAmount", "payAmount")
        )
    except (InvalidOperation, ValueError, TypeError):
        return False


def created_for_attempt(row, created_at):
    try:
        created = datetime.strptime(row["createdTime"], "%Y-%m-%d %H:%M:%S")
        zone = ZoneInfo("Asia/Shanghai")
        start = aware(created_at).astimezone(zone).replace(tzinfo=None, microsecond=0)
        return start <= created <= datetime.now(zone).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError):
        return False


async def confirm_original(state, owner, payload, candidates, observations, budget):
    if not payload.get("prepay_id") or not candidates:
        return False
    credential = await state.school_credentials.current(owner)
    user = state.school_credentials.payload(credential)["school_user_id"]
    owned = [item for item in candidates if item.get("userId") == str(user)]
    if len(owned) != 1:
        return False
    transport = PaymentTransport(state.school_store)
    async with transport.client() as client:
        # 只GET本地原单保存的已验证支付URL，不重放任何支付表单。
        page = await transport.request(client, "GET", payload["pay_url"], budget)
    confirmed = original_order_paid(page.text)
    observations["original_payment_page"] = {"paid_confirmed": confirmed}
    return confirmed


async def paid_order(sessions, owner, request_id, row, payload, observations, budget,
                     *, confirm=None):
    matches, candidates, expected_pages = [], [], None
    for current in range(1, 6):
        value = await sessions.read(
            owner, request_id, "/base/order/page",
            {"buildId": payload["school_room_id"],
             "startTimeStr": aware(row["created_at"]).astimezone(ZoneInfo("Asia/Shanghai"))
             .date().isoformat(),
             "endTimeStr": today().isoformat(), "current": current, "size": 10,
             "pageTotal": 100, "orderType": 0, "payMethod": 1, "payStatus": 2},
            budget=min(20, budget.remaining()), read_timeout=15,
        )
        rows, pages = order_page(value, current)
        observations[f"D04-{current}"] = {"records": rows, "pages": pages}
        if pages > 5 or (expected_pages is not None and pages != expected_pages):
            return False
        expected_pages = pages
        matches.extend(item for item in rows if same_order(item, payload))
        candidates.extend(item for item in rows if confirms_paid(item, payload)
                          and created_for_attempt(item, row["created_at"]))
        if current >= pages:
            if matches:
                return len(matches) == 1 and confirms_paid(matches[0], payload)
            return bool(confirm and await confirm(candidates))
    return False
