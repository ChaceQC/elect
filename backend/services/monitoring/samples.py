"""固定实际成员的30分钟快照；不靠时间上界排除迟到提交。"""

import hashlib
from datetime import UTC
from uuid import UUID

from services.common.dates import utc_bounds
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import aware, execute, first

from .dto import Sample, Samples
from .sample_snapshots import create_or_reuse

PAGE_SQL = (
    "SELECT p.*,previous.captured_at AS previous_captured_at,"
    "COALESCE(p.capture_interval_minutes,m.interval_minutes) AS interval_minutes,"
    "CASE WHEN p.meter_source_record_key IS NULL OR p.meter_source_record_key='' THEN 0 "
    "ELSE EXISTS(SELECT 1 FROM monitor_samples other WHERE "
    "other.binding_id=p.binding_id AND other.owner_user_id=p.owner_user_id "
    "AND other.meter_source_record_key=p.meter_source_record_key "
    "AND other.captured_at<p.captured_at) END AS meter_is_repeated "
    "FROM sample_snapshot_items i JOIN monitor_samples p ON p.id=i.sample_id "
    "JOIN monitors m ON m.id=p.monitor_id "
    "LEFT JOIN monitor_samples previous ON previous.id=p.previous_sample_id "
    "WHERE i.snapshot_id=:snapshot AND i.position>:offset "
    "ORDER BY i.position LIMIT :size"
)


def sample_view(row):
    gap = (
        int((row["captured_at"] - row["previous_captured_at"]).total_seconds())
        if row["previous_captured_at"]
        else None
    )
    return Sample(
        id=UUID(bytes=row["id"]),
        run_id=UUID(bytes=row["run_id"]),
        captured_at=aware(row["captured_at"]),
        balance=format(row["balance"], ".2f"),
        previous_captured_at=aware(row["previous_captured_at"]),
        balance_delta=format(row["balance_delta"], ".2f")
        if row["balance_delta"] is not None
        else None,
        balance_delta_kind="net_balance_change",
        gap_seconds=gap,
        gap_detected=gap is not None and gap > row["interval_minutes"] * 60 * 2,
        meter_last_reading=format(row["meter_last_reading"], ".4f")
        if row["meter_last_reading"] is not None
        else None,
        meter_reading=format(row["meter_reading"], ".4f")
        if row["meter_reading"] is not None
        else None,
        meter_delta=format(row["meter_delta"], ".4f") if row["meter_delta"] is not None else None,
        meter_record_date=row["meter_record_date"],
        meter_source="school_C02_daily_record" if row["meter_record_date"] else None,
        meter_source_record_key=row["meter_source_record_key"],
        meter_is_repeated=bool(row["meter_is_repeated"]),
        quality=row["quality"],
    )


async def snapshot(conn, owner, command, start, end, token_key):
    token = command.snapshot_token
    if token:
        row = await first(
            conn,
            "SELECT *,expires_at>UTC_TIMESTAMP(6) AS valid FROM sample_snapshots WHERE "
            "token_hash=:hash AND owner_user_id=:owner FOR SHARE",
            hash=hashlib.sha256(token.encode()).digest(),
            owner=owner.bytes,
        )
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "快照不存在")
        if (
            row["binding_id"] != command.binding_id.bytes
            or row["start_date"] != command.start_date
            or row["end_date"] != command.end_date
        ):
            raise ApiError(400, ErrorCode.SNAPSHOT_MISMATCH, "快照与寝室或日期范围不同")
        if not row["valid"]:
            raise ApiError(410, ErrorCode.SNAPSHOT_EXPIRED, "快照已过期，请从第一页重新读取")
        return token, row
    if command.page != 1:
        raise ApiError(400, ErrorCode.SNAPSHOT_MISMATCH, "后续分页必须携带首页快照")
    return await create_or_reuse(conn, owner, command, start, end, token_key)


async def list_samples(engine, owner, command, token_key):
    start, end = utc_bounds(command.start_date, command.end_date)
    async with engine.begin() as conn:
        token, fixed = await snapshot(conn, owner, command, start, end, token_key)
        rows = (
            (
                await execute(
                    conn,
                    PAGE_SQL,
                    snapshot=fixed["id"],
                    offset=(command.page - 1) * command.page_size,
                    size=command.page_size,
                )
            )
            .mappings()
            .all()
        )
        monitor = await first(
            conn,
            "SELECT first_enabled_at FROM monitors WHERE owner_user_id=:owner",
            owner=owner.bytes,
        )
        history = await first(
            conn,
            "SELECT 1 AS found FROM monitor_samples WHERE owner_user_id=:owner AND "
            "binding_id=:binding LIMIT 1",
            owner=owner.bytes,
            binding=command.binding_id.bytes,
        )
    return Samples(
        items=[sample_view(row) for row in rows],
        page=command.page,
        page_size=command.page_size,
        total=fixed["total"],
        has_monitor_history=bool(history or monitor and monitor["first_enabled_at"]),
        snapshot_token=token,
        snapshot_expires_at=fixed["expires_at"].replace(tzinfo=UTC),
    )
