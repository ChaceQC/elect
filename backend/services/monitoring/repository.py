"""监控本域的控制行锁与审计；全部写操作从 monitor 开始加锁。"""

from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first


async def lock_monitor(conn, owner):
    await execute(
        conn,
        "INSERT INTO monitors (id,owner_user_id,desired_enabled,state,health,"
        "interval_minutes,repeat_limit,threshold,email_version,version,generation,"
        "consecutive_failures) VALUES (:id,:owner,0,'disabled','unavailable',60,2,20,1,1,1,0) "
        "ON DUPLICATE KEY UPDATE owner_user_id=owner_user_id",
        id=new_id().bytes,
        owner=owner.bytes,
    )
    return await first(
        conn, "SELECT * FROM monitors WHERE owner_user_id=:owner FOR UPDATE", owner=owner.bytes
    )


def require_version(actual, expected):
    if expected != actual:
        raise ApiError(
            409, ErrorCode.VERSION_CONFLICT, "状态已更新，请刷新后再操作", current_version=actual
        )


async def audit(conn, monitor, request_id, action):
    await record_audit(
        conn,
        "monitoring",
        action,
        "monitor",
        UUID(bytes=monitor["id"]),
        request_id,
        actor=UUID(bytes=monitor["owner_user_id"]),
        version=monitor["version"] + 1,
    )


async def invalidate(conn, monitor, *, close_episode=True):
    """monitor 锁已持有；保留在途事实，提升 epoch 拒绝迟到提交。"""
    await execute(
        conn,
        "UPDATE monitor_runs SET execution_epoch=execution_epoch+1,version=version+1,"
        "cancel_requested_at=UTC_TIMESTAMP(6),"
        "finished_at=IF(state IN ('pending','retry_wait'),UTC_TIMESTAMP(6),finished_at),"
        "state=IF(state IN ('running','cancel_requested'),'cancel_requested','cancelled'),"
        "next_attempt_at=NULL,updated_at=UTC_TIMESTAMP(6) WHERE monitor_id=:id "
        "AND state IN ('pending','retry_wait','running')",
        id=monitor["id"],
    )
    await execute(
        conn,
        "UPDATE alert_episodes SET generation=:generation,"
        "state=IF(:close,'closed',state),"
        "closed_at=IF(:close,UTC_TIMESTAMP(6),closed_at),updated_at=UTC_TIMESTAMP(6) "
        "WHERE monitor_id=:id AND state='open'",
        id=monitor["id"],
        generation=monitor["generation"] + 1,
        close=close_episode,
    )
    await execute(
        conn,
        "UPDATE alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
        "SET s.state='cancelled',s.finished_at=UTC_TIMESTAMP(6),"
        "s.updated_at=UTC_TIMESTAMP(6) WHERE e.monitor_id=:id AND s.state='reserved'",
        id=monitor["id"],
    )
    await execute(
        conn,
        "UPDATE monitors SET current_episode_id=IF(:close,NULL,current_episode_id),"
        "active_run_id=NULL WHERE id=:id",
        id=monitor["id"],
        close=close_episode,
    )


async def in_flight(conn, monitor):
    runs = await first(
        conn,
        "SELECT COUNT(*) AS n FROM monitor_runs WHERE monitor_id=:id "
        "AND state IN ('running','cancel_requested') AND lease_until>UTC_TIMESTAMP(6)",
        id=monitor["id"],
    )
    mails = await first(
        conn,
        "SELECT COUNT(*) AS n FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
        "WHERE e.monitor_id=:id AND s.state='authorized'",
        id=monitor["id"],
    )
    return runs["n"] + mails["n"], mails["n"]
