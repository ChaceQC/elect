"""上海日期聚合：边缘桶裁剪到选择范围，未知日不补零。"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from services.common.dates import check_range
from services.common.sql import aware, execute, first

from .dto import Consumption
from .query_jobs import target


def bucket_end(day, granularity):
    if granularity == "day":
        return day
    if granularity == "week":
        return day + timedelta(days=6 - day.weekday())
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def totals(rows, expected):
    amounts = [row["charged_amount"] for row in rows if row["charged_amount"] is not None]
    usage = [row["energy_usage"] for row in rows if row["energy_usage"] is not None]
    return {
        "amount": format(sum(map(Decimal, amounts)), ".2f") if amounts else None,
        "energy_usage": format(sum(map(Decimal, usage)), ".4f") if usage else None,
        "known_days": len(
            {row["record_date"] for row in rows if row["charged_amount"] is not None}
        ),
        "expected_days": expected,
        # C02 成功/有记录尚不能证明全日完整。
        "complete": False,
    }


def aggregate(rows, start, end, granularity):
    by_day = defaultdict(list)
    for row in rows:
        if start <= row["record_date"] <= end:
            by_day[row["record_date"]].append(row)
    buckets, day = [], start
    while day <= end:
        stop = min(bucket_end(day, granularity), end)
        selected, cursor = [], day
        while cursor <= stop:
            selected.extend(by_day[cursor])
            cursor += timedelta(days=1)
        buckets.append(
            {"start_date": day, "end_date": stop, **totals(selected, (stop - day).days + 1)}
        )
        day = stop + timedelta(days=1)
    summary = totals([row for values in by_day.values() for row in values], (end - start).days + 1)
    return buckets, summary


async def consumption(engine, owner, command):
    check_range(command.start_date, command.end_date)
    async with engine.begin() as conn:
        await target(conn, owner, command.binding_id)
        rows = (
            (
                await execute(
                    conn,
                    "SELECT record_date,charged_amount,energy_usage FROM "
                    "school_history_records WHERE binding_id=:binding AND "
                    "source='C02' AND record_date BETWEEN :start AND :end ORDER BY "
                    "record_date,id",
                    binding=command.binding_id.bytes,
                    start=command.start_date,
                    end=command.end_date,
                )
            )
            .mappings()
            .all()
        )
        sync = await first(
            conn,
            "SELECT o.* FROM history_syncs s JOIN room_operations o ON "
            "o.id=s.operation_id WHERE s.binding_id=:binding AND "
            "s.requested_start<=:end AND s.requested_end>=:start ORDER BY "
            "s.created_at DESC,s.id DESC LIMIT 1",
            binding=command.binding_id.bytes,
            start=command.start_date,
            end=command.end_date,
        )
        version = await first(
            conn,
            "SELECT COALESCE(SUM(version),0)+1 AS n FROM history_syncs WHERE binding_id=:binding",
            binding=command.binding_id.bytes,
        )
    buckets, summary = aggregate(rows, command.start_date, command.end_date, command.granularity)
    coverage = (
        "partial"
        if summary["amount"] is not None or summary["energy_usage"] is not None
        else "unknown"
    )
    state = (
        "loading"
        if sync and sync["state"] in {"accepted", "running"}
        else "stale"
        if sync and sync["state"] == "failed" and rows
        else "failed"
        if sync and sync["state"] == "failed"
        else "partial"
        if rows
        else "empty"
    )
    return Consumption(
        **command.model_dump(),
        buckets=buckets,
        summary=summary,
        coverage=coverage,
        sync_status=state,
        sync_operation={
            "id": UUID(bytes=sync["id"]),
            "type": sync["type"],
            "state": sync["state"],
            "target_binding_id": command.binding_id,
            "created_at": aware(sync["created_at"]),
        }
        if sync
        else None,
        version=int(version["n"]),
    )
