"""手动请求映射预算；Scheduler不插入映射、不消费此额度。"""

from services.common.admission import enforce_budget
from services.common.sql import first


async def check_budget(conn, owner):
    recent = await first(
        conn, "SELECT COUNT(*) AS daily,COALESCE(SUM(created_at>"
        "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 MINUTE)),0) AS minute,"
        "MIN(created_at) AS earliest,UTC_TIMESTAMP(6) AS now FROM monitor_run_requests "
        "WHERE owner_user_id=:owner AND created_at>DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 DAY)",
        owner=owner.bytes,
    )
    pending = await first(
        conn, "SELECT COUNT(*) AS n FROM monitor_run_requests q JOIN monitor_runs r "
        "ON r.id=q.run_id WHERE q.owner_user_id=:owner "
        "AND r.state NOT IN ('succeeded','failed','cancelled')", owner=owner.bytes,
    )
    enforce_budget(recent, pending["n"], daily=48)
