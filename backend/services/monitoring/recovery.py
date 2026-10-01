"""到期租约接管和丢失唤醒重建；旧 epoch 永远失去提交资格。"""

from services.common.ids import new_id
from services.common.sql import execute, first

from .results import finish_attempt
from .scheduler import wake


async def recover_run(conn, monitor, run):
    cancelled = (
        run["state"] == "cancel_requested"
        or not monitor["desired_enabled"]
        or monitor["state"] != "active"
        or monitor["active_run_id"] != run["id"]
        or monitor["generation"] != run["generation"]
        or monitor["binding_id"] != run["binding_id"]
        or monitor["credential_version"] != run["credential_version"]
    )
    exhausted = run["attempt_count"] >= 3
    state = "cancelled" if cancelled else "failed" if exhausted else "retry_wait"
    await finish_attempt(
        conn,
        run,
        "cancelled" if cancelled else "failed" if exhausted else "retryable",
        None if cancelled else "SCHOOL_TIMEOUT",
    )
    await execute(
        conn,
        "UPDATE monitor_runs SET state=:state,execution_epoch=execution_epoch+1,"
        "version=version+1,error_code=:error,lease_owner=NULL,lease_until=NULL,"
        "next_attempt_at=IF(:terminal,NULL,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND)),"
        "finished_at=IF(:terminal,UTC_TIMESTAMP(6),NULL),updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
        id=run["id"],
        state=state,
        terminal=cancelled or exhausted,
        error=None if cancelled else "SCHOOL_TIMEOUT",
    )
    if cancelled or exhausted:
        await execute(
            conn,
            "UPDATE monitors SET active_run_id=NULL WHERE id=:id AND active_run_id=:run",
            id=monitor["id"],
            run=run["id"],
        )
    if exhausted and not cancelled:
        from .faults import cycle_failed

        await cycle_failed(conn, monitor, "SCHOOL_TIMEOUT")
        await execute(
            conn,
            "UPDATE monitors SET health=IF(last_success_at IS "
            "NULL,'unavailable','degraded'),last_error_code='SCHOOL_TIMEOUT',consecutive_fa"
            "ilures=consecutive_failures+1 WHERE id=:id",
            id=monitor["id"],
        )


async def recovery_tick(engine):
    async with engine.begin() as conn:
        monitors = (
            (
                await execute(
                    conn,
                    "SELECT * FROM monitors WHERE id IN (SELECT monitor_id FROM monitor_runs "
                    "WHERE (state IN ('running','cancel_requested') AND "
                    "lease_until<=UTC_TIMESTAMP(6)) "
                    "OR (state IN ('pending','retry_wait') AND next_attempt_at<=UTC_TIMESTAMP(6) "
                    "AND updated_at<=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 15 SECOND))) "
                    "ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED",
                )
            )
            .mappings()
            .all()
        )
        for monitor in monitors:
            runs = (
                (
                    await execute(
                        conn,
                        "SELECT * FROM monitor_runs WHERE monitor_id=:id AND "
                        "((state IN ('running','cancel_requested') AND "
                        "lease_until<=UTC_TIMESTAMP(6)) "
                        "OR (state IN ('pending','retry_wait') AND "
                        "next_attempt_at<=UTC_TIMESTAMP(6) "
                        "AND updated_at<=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 15 SECOND))) "
                        "ORDER BY id FOR UPDATE",
                        id=monitor["id"],
                    )
                )
                .mappings()
                .all()
            )
            for run in runs:
                if run["state"] in {"running", "cancel_requested"}:
                    await recover_run(conn, monitor, run)
                elif (
                    run["generation"] != monitor["generation"]
                    or monitor["active_run_id"] != run["id"]
                    or monitor["state"] != "active"
                ):
                    await recover_run(conn, monitor, run)
                else:
                    await wake(conn, run, new_id())
                    await execute(
                        conn,
                        "UPDATE monitor_runs SET updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                        id=run["id"],
                    )
    return bool(monitors)


async def acknowledge_cancel(engine, execution):
    async with engine.begin() as conn:
        monitor = await first(
            conn, "SELECT id FROM monitors WHERE id=:id FOR UPDATE", id=execution.monitor_id.bytes
        )
        run = await first(
            conn, "SELECT * FROM monitor_runs WHERE id=:id FOR UPDATE", id=execution.run_id.bytes
        )
        if (
            not monitor
            or not run
            or run["state"] != "cancel_requested"
            or run["lease_owner"] != execution.lease_owner
        ):
            return False
        await finish_attempt(conn, run, "cancelled")
        await execute(
            conn,
            "UPDATE monitor_runs SET state='cancelled',version=version+1,finished_at=UTC_TI"
            "MESTAMP(6),lease_owner=NULL,lease_until=NULL,updated_at=UTC_TIMESTAMP(6) "
            "WHERE id=:id",
            id=run["id"],
        )
        await execute(
            conn,
            "UPDATE monitors SET active_run_id=NULL WHERE id=:id AND active_run_id=:run",
            id=monitor["id"],
            run=run["id"],
        )
    return True
