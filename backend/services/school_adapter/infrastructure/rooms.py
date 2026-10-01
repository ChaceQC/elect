from decimal import Decimal, InvalidOperation

from services.common.errors import ErrorCode
from services.common.http import ApiError


def opaque_id(value):
    if (
        not isinstance(value, (str, int))
        or isinstance(value, bool)
        or not 1 <= len(str(value)) <= 128
    ):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校房间标识异常")
    return str(value)


def money(value):
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) >= Decimal("1000000000000"):
            raise InvalidOperation()
        if amount != amount.quantize(Decimal(".01")):
            raise InvalidOperation()
        return format(amount.quantize(Decimal(".01")), ".2f")
    except (InvalidOperation, ValueError, TypeError):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校余额字段异常") from None


def room_record(raw):
    if not isinstance(raw, dict):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校房间记录异常")
    building, number = str(raw.get("buildingName") or ""), str(raw.get("roomNo") or "")
    if len(building) > 128 or len(number) > 64:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校房间名称异常")
    return {
        "room_id": opaque_id(raw.get("roomId")),
        "building": building,
        "number": number,
        "display_name": " ".join(filter(None, [building, number])) or "学校寝室",
        "meter_code": str(raw["meterCode"])[:128] if raw.get("meterCode") else None,
        "relation_id": str(raw["id"])[:128] if raw.get("id") else None,
        "balance": money(raw.get("balance")),
    }


def bound_rooms(value):
    records = value.get("data")
    if not isinstance(records, list) or len(records) > 1000:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校绑定列表结构异常")
    normalized = [room_record(record) for record in records]
    if len({row["room_id"] for row in normalized}) != len(normalized):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校绑定记录重复")
    return normalized
