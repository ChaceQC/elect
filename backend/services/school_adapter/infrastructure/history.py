"""C02 白名单解析；记录归属由请求上下文确定。"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from services.common.errors import ErrorCode
from services.common.http import ApiError


def decimal_field(value, places, limit):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = Decimal(str(value))
        scale = Decimal(10) ** -places
        if not number.is_finite() or abs(number) >= limit or number != number.quantize(scale):
            raise ValueError()
        return format(number, f".{places}f")
    except (ValueError, InvalidOperation):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校历史数值字段异常") from None


def record_date(raw):
    for key, pattern in (("time", "%Y-%m-%d"), ("statTime", "%Y%m%d")):
        value = raw.get(key)
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.strptime(value, pattern).date()
            if parsed.strftime(pattern) == value:
                return parsed
        except ValueError:
            continue
    raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校历史日期异常")


def records(value, start, end):
    data = value.get("data")
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校历史列表结构异常")
    normalized = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校历史行结构异常")
        day = record_date(raw)
        if not start <= day <= end:
            # 参数/范围语义变更时整个窗口失败，保留原快照。
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校历史返回区间外日期")
        status = raw.get("trueAmountName")
        if status is not None and (not isinstance(status, str) or len(status) > 128):
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校扣费状态异常")
        row = {
            "record_date": day.isoformat(),
            "last_reading": decimal_field(raw.get("lastReading"), 4, 10**14),
            "reading": decimal_field(raw.get("reading"), 4, 10**14),
            "energy_usage": decimal_field(raw.get("energyUsage"), 4, 10**14),
            "charged_amount": decimal_field(raw.get("trueAmount"), 2, 10**12),
            "charge_status": status,
            "quality": "unverified_coverage",
        }
        row["row_hash"] = hashlib.sha256(
            json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        normalized.append(row)
    return normalized
