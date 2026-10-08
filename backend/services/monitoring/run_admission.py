"""用户触发采集共用映射预算；定期Scheduler不插入映射、不消费此额度。"""

import hashlib

from services.common.admission import enforce_budget
from services.common.sql import execute, first


async def record_request(conn, owner, key_hash, run_id):
    await execute(
        conn,
        "INSERT INTO monitor_run_requests (owner_user_id,idempotency_key_hash,request_digest,"
        "run_id,expires_at) VALUES (:owner,:key,:digest,:run,"
        "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 180 DAY))",
        owner=owner.bytes,
        key=key_hash,
        digest=hashlib.sha256(b"manual_run").digest(),
        run=run_id,
    )


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
