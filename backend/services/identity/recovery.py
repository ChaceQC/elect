from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .application.login_gate import LoginBusy


async def recover_tick(app, *, stop=None):
    from .revocation import recover_revocation

    activity = False
    try:
        activity = await recover_revocation(app)
    except LoginBusy:
        await require_healthy_recovery(app)
        return False
    if activity:
        await require_healthy_recovery(app)
        return True
    if stop and stop.is_set():
        return False
    async with app.state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE login_attempts SET state='expired',updated_at=UTC_TIMESTAMP(6) "
            "WHERE expires_at <= UTC_TIMESTAMP(6) AND state IN "
            "('created','authenticating','staged')",
        )
        rows = (
            (
                await execute(
                    conn,
                    "SELECT id FROM login_attempts WHERE state IN "
                    "('authenticating','staged','identity_committed','activating') "
                    "AND next_reconcile_at<=UTC_TIMESTAMP(6) "
                    "AND updated_at<DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 5 SECOND) "
                    "ORDER BY next_reconcile_at LIMIT 5",
                )
            )
            .mappings()
            .all()
        )
    activity = await recover_attempts(app.state.login_saga, rows, stop)
    await require_healthy_recovery(app)
    return activity


async def recover_attempts(saga, rows, stop):
    activity = False
    for item in rows:
        if stop and stop.is_set():
            break
        attempt_id = UUID(bytes=item["id"])
        try:
            async with saga.locked(attempt_id, background=True):
                row = await saga.read(attempt_id)
                if row["state"] not in {
                    "authenticating",
                    "staged",
                    "identity_committed",
                    "activating",
                }:
                    continue
                await saga.advance(row, new_id())
                activity = True
        except LoginBusy:
            continue
        except ApiError as error:
            # 提交身份前的暂存404可终结旧尝试；状态查询限流/依赖故障仍需恢复。
            if (error.code != ErrorCode.RATE_LIMITED
                    and error.status < 500
                    and await saga.reject_uncommitted(attempt_id, error.code)):
                activity = True
            else:
                # 不回写旧阶段；前台可能已推进或终结。只给仍待恢复的行保存失败和退避。
                async with saga.engine.begin() as conn:
                    await execute(
                        conn,
                        "UPDATE login_attempts SET error_code=:error,"
                        "next_reconcile_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 5 SECOND) "
                        "WHERE id=:id AND state IN "
                        "('authenticating','staged','identity_committed','activating')",
                        id=attempt_id.bytes, error=error.code,
                    )
    return activity


async def require_healthy_recovery(app):
    # 到期候选为空、执行门忙或其他任务成功，不代表已有失败已恢复。
    async with app.state.database.connect() as conn:
        pending = await first(
            conn,
            "SELECT EXISTS(SELECT 1 FROM login_attempts WHERE state IN "
            "('authenticating','staged','identity_committed','activating') "
            "AND error_code IS NOT NULL) OR EXISTS(SELECT 1 FROM credential_operations "
            "WHERE state IN ('accepted','running','reconciling') "
            "AND error_code IS NOT NULL) AS failed",
        )
    if pending["failed"]:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "身份恢复尚未成功", True)
