"""最近C02日记录的辅助读数；加密缓存和失败均不替代新鲜余额。"""

import asyncio
from datetime import timedelta
from decimal import Decimal

from services.common.dates import today
from services.common.http import ApiError

from ..infrastructure.history import records


def latest_meter(rows):
    if not rows:
        return None
    day = max(row["record_date"] for row in rows)
    latest = {row["row_hash"]: row for row in rows if row["record_date"] == day}
    # 同日多个不同记录无法确定同一电表，不能拼接或任意选择起止码。
    if len(latest) != 1:
        return None
    row = next(iter(latest.values()))
    if row["last_reading"] is None or row["reading"] is None:
        return None
    delta = Decimal(row["reading"]) - Decimal(row["last_reading"])
    if abs(delta) >= 10**14:
        return None
    quality = "meter_not_realtime"
    if delta < 0:
        quality = "meter_negative_delta"
    elif row["energy_usage"] is not None and delta != Decimal(row["energy_usage"]):
        quality = "meter_inconsistent"
    return {
        "last_reading": row["last_reading"], "reading": row["reading"],
        "delta": format(delta, ".4f"), "record_date": day,
        "source_record_key": row["row_hash"], "quality": quality,
    }


async def collect_meter(sessions, owner, binding, room, request_id, budget):
    try:
        async with asyncio.timeout(min(20, budget.remaining())):
            end = today()
            key = f"school_adapter:meter:{owner}:{binding}:{end}"
            cached = await sessions.store.get_secret(key)
            if cached is not None:
                return cached["meter"]
            start = end - timedelta(days=6)
            value = await sessions.read(
                owner, request_id, "/base/record/queryRecordByTime",
                {"buildId": room, "startTimeStr": start.strftime("%Y%m%d"),
                 "endTimeStr": end.strftime("%Y%m%d")},
                budget=min(20, budget.remaining()), read_timeout=15,
            )
            meter = latest_meter(records(value, start, end))
            try:
                await sessions.store.put_secret(key, {"meter": meter}, ttl=10800 if meter else 600)
            except ApiError:
                pass
            return meter
    except (ApiError, TimeoutError):
        return None
