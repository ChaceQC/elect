"""学校日金额优先、监控余额估算补缺；两类来源合并后再聚合。"""

from decimal import Decimal

from services.common.http import ApiError
from services.room.consumption import aggregate, coverage_status
from services.room.dto import Consumption


def estimate_totals(rows):
    amounts = [Decimal(row["charged_amount"]) for row in rows if row["estimated"]]
    return {
        "estimated_amount": format(sum(amounts), ".2f") if amounts else None,
        "estimated_days": len(amounts),
    }


def merge_consumption(history, estimates, granularity):
    original = Consumption.model_validate(history)
    by_day = {row["record_date"]: row["amount"] for row in estimates["days"]}
    rows = []
    for bucket in original.buckets:
        estimate = by_day.get(bucket.start_date.isoformat())
        use_estimate = estimate is not None and (
            bucket.amount is None or Decimal(bucket.amount) == 0 and Decimal(estimate) > 0
        )
        rows.append({
            "record_date": bucket.start_date,
            "charged_amount": estimate if use_estimate else bucket.amount,
            "energy_usage": bucket.energy_usage,
            "estimated": use_estimate,
        })
    buckets, summary = aggregate(rows, original.start_date, original.end_date, granularity)
    for bucket in buckets:
        bucket.update(estimate_totals([
            row for row in rows if bucket["start_date"] <= row["record_date"] <= bucket["end_date"]
        ]))
    summary.update(estimate_totals(rows))
    state = original.sync_status
    if state in {"ready", "partial", "empty"}:
        state = "ready" if summary["complete"] else (
            "partial" if coverage_status(summary) != "unknown" else "empty"
        )
    return Consumption.model_validate({
        **original.model_dump(), "granularity": granularity,
        "buckets": buckets, "summary": summary,
        "coverage": coverage_status(summary), "sync_status": state,
        "version": original.version + estimates["sample_count"],
        "monitoring_status": "ready",
    }).model_dump(mode="json")


async def with_monitoring(request, principal, history, granularity):
    # 调用方必须先取得Room本人绑定的日历史，不以可猜测binding_id直接查询。
    try:
        estimates = await request.app.state.service_client.call(
            "monitoring", "/browser/consumption", "monitor:browser", principal.request_id,
            {key: history[key] for key in ("binding_id", "start_date", "end_date")},
            principal=principal, budget=5,
        )
    except (ApiError, TimeoutError):
        value = merge_consumption(history, {"days": [], "sample_count": 0}, granularity)
        value["monitoring_status"] = "unavailable"
        return value
    return merge_consumption(history, estimates, granularity)
