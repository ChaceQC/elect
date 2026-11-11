"""历史任务受理预算；调用方必须已持有本人偏好行锁。"""

from math import ceil

from services.common.dates import windows
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import first

OPERATIONS_PER_MINUTE = 20
OPERATIONS_PER_DAY = 120
MAX_PENDING_OPERATIONS = 32
MAX_PENDING_SYNCS = 4
MAX_PENDING_WINDOWS = 128


async def covering_sync(conn, owner, binding, command):
    return await first(
        conn, "SELECT operation_id FROM history_syncs WHERE owner_user_id=:owner "
        "AND binding_id=:binding AND requested_start<=:start AND requested_end>=:end "
        "AND status IN ('accepted','running') ORDER BY created_at,id LIMIT 1",
        owner=owner.bytes, binding=binding.bytes, start=command.start_date, end=command.end_date,
    )


def limited(message, retry=60):
    return ApiError(429, ErrorCode.RATE_LIMITED, message, True, retry_after_seconds=retry)


async def check_admission(conn, owner, binding, command):
    await check_operation_budget(conn, owner)
    if await covering_sync(conn, owner, binding, command):
        return
    syncs = await first(
        conn, "SELECT COUNT(*) AS n FROM history_syncs WHERE owner_user_id=:owner "
        "AND status IN ('accepted','running')", owner=owner.bytes,
    )
    pending = await first(
        conn, "SELECT COUNT(*) AS n FROM history_sync_windows w JOIN history_syncs s "
        "ON s.id=w.sync_id WHERE s.owner_user_id=:owner "
        "AND w.state IN ('pending','running','retry_wait')", owner=owner.bytes,
    )
    size = len(list(windows(command.start_date, command.end_date)))
    if syncs["n"] >= MAX_PENDING_SYNCS or pending["n"] + size > MAX_PENDING_WINDOWS:
        raise limited("已有历史同步等待处理，请等待完成后重试")


async def check_operation_budget(conn, owner):
    recent = await first(
        conn, "SELECT COUNT(*) AS daily,COALESCE(SUM(created_at>"
        "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 MINUTE)),0) AS minute,"
        "MIN(CASE WHEN created_at>DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 MINUTE) "
        "THEN created_at END) AS minute_earliest,"
        "MIN(created_at) AS earliest,UTC_TIMESTAMP(6) AS now FROM room_operations "
        "WHERE owner_user_id=:owner AND type='history_sync' "
        "AND created_at>DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 DAY)", owner=owner.bytes,
    )
    pending = await first(
        conn, "SELECT COUNT(*) AS n FROM room_operations WHERE owner_user_id=:owner "
        "AND type='history_sync' AND state IN ('accepted','running','reconciling','unknown')",
        owner=owner.bytes,
    )
    retry = 0
    message = "历史同步请求过于频繁，请稍后重试"
    if recent["daily"] >= OPERATIONS_PER_DAY:
        retry = max(1, ceil(86400 - (recent["now"] - recent["earliest"]).total_seconds()))
        message = "今日历史同步次数已达上限，请稍后重试"
    if recent["minute"] >= OPERATIONS_PER_MINUTE:
        retry = max(retry, ceil(60 - (recent["now"] - recent["minute_earliest"]).total_seconds()))
    if pending["n"] >= MAX_PENDING_OPERATIONS:
        retry = max(retry, 60)
        message = "已有历史同步等待处理，请等待完成后重试"
    if retry:
        raise limited(message, retry)
