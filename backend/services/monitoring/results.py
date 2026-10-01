"""唯一成功样本、运行终态与基线在同一栅栏事务中提交。"""

import random
from decimal import Decimal

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.ids import new_id
from services.common.sql import execute, first

from .alerts import on_sample
from .faults import cycle_failed, cycle_succeeded
from .fences import fenced_transaction


async def finish_attempt(conn, run, outcome, error=None):
    await execute(
        conn,
        "UPDATE monitor_attempts SET outcome=:outcome,error_code=:error,"
        "finished_at=UTC_TIMESTAMP(6),duration_ms=TIMESTAMPDIFF(MICROSECOND,"
        "started_at,UTC_TIMESTAMP(6)) DIV 1000 WHERE run_id=:run AND attempt_no=:attempt "
        "AND outcome='running'",
        run=run["id"],
        attempt=run["attempt_count"],
        outcome=outcome,
        error=error,
    )


async def succeed(engine, execution, balance, request_id):
    async with fenced_transaction(engine, execution) as (conn, monitor, run):
        sample_id = new_id()
        previous = (
            await first(
                conn,
                "SELECT * FROM monitor_samples WHERE id=:id AND binding_id=:binding AND "
                "owner_user_id=:owner",
                id=monitor["last_sample_id"],
                binding=run["binding_id"],
                owner=monitor["owner_user_id"],
            )
            if monitor["last_sample_id"]
            else None
        )
        await execute(
            conn,
            "INSERT INTO monitor_samples (id,run_id,monitor_id,owner_user_id,binding_id,"
            "captured_at,balance,previous_sample_id,balance_delta,quality,credential_version,"
            "capture_interval_minutes) "
            "VALUES (:id,:run,:monitor,:owner,:binding,UTC_TIMESTAMP(6),:balance,:previous,"
            ":delta,'balance_only',:credential,:interval)",
            id=sample_id.bytes,
            run=run["id"],
            monitor=monitor["id"],
            owner=monitor["owner_user_id"],
            binding=run["binding_id"],
            balance=balance,
            previous=previous["id"] if previous else None,
            delta=Decimal(balance) - previous["balance"] if previous else None,
            credential=execution.credential_version,
            interval=monitor["interval_minutes"],
        )
        await finish_attempt(conn, run, "succeeded")
        await execute(
            conn,
            "UPDATE monitor_runs SET state='succeeded',version=version+1,finished_at=UTC_TI"
            "MESTAMP(6),lease_owner=NULL,lease_until=NULL,error_code=NULL WHERE id=:id",
            id=run["id"],
        )
        await execute(
            conn,
            "UPDATE monitors SET active_run_id=NULL,last_sample_id=:sample,last_success_at="
            "UTC_TIMESTAMP(6),health='healthy',last_error_code=NULL,consecutive_failures=0 "
            "WHERE id=:id",
            id=monitor["id"],
            sample=sample_id.bytes,
        )
        await record_audit(
            conn,
            "monitoring",
            "monitor.sample_captured",
            "run",
            execution.run_id,
            request_id,
            actor=None,
            version=run["version"] + 1,
        )
        await cycle_succeeded(conn, monitor)
        await on_sample(conn, monitor, sample_id, request_id)
    return sample_id


async def fail(engine, execution, error, retryable, request_id, retry_after=None):
    async with fenced_transaction(engine, execution) as (conn, monitor, run):
        retry = retryable and run["attempt_count"] < 3 and error != ErrorCode.SCHOOL_REAUTH_REQUIRED
        delay = (30 if run["attempt_count"] == 1 else 120) + random.uniform(0, 5)
        delay = max(delay, retry_after or 0)
        await finish_attempt(conn, run, "retryable" if retry else "failed", error)
        await execute(
            conn,
            "UPDATE monitor_runs SET state=:state,version=version+1,error_code=:error,next_"
            "attempt_at=IF(:retry,TIMESTAMPADD(SECOND,:delay,UTC_TIMESTAMP(6)),NULL),finish"
            "ed_at=IF(:retry,NULL,UTC_TIMESTAMP(6)),lease_owner=NULL,lease_until=NULL "
            "WHERE id=:id",
            id=run["id"],
            state="retry_wait" if retry else "failed",
            error=error,
            retry=retry,
            delay=delay,
        )
        reauth = error == ErrorCode.SCHOOL_REAUTH_REQUIRED
        await execute(
            conn,
            "UPDATE monitors SET active_run_id=IF(:retry,active_run_id,NULL),health=IF(last"
            "_success_at IS NULL,'unavailable','degraded'),last_error_code=:error,consecuti"
            "ve_failures=consecutive_failures+1,state=IF(:reauth,'requires_reauth',state),n"
            "ext_run_at=IF(:reauth,NULL,next_run_at) WHERE id=:id",
            id=monitor["id"],
            retry=retry,
            error=error,
            reauth=reauth,
        )
        if retry:
            from .scheduler import wake

            updated = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=run["id"])
            event = await wake(conn, updated, request_id)
            await execute(
                conn,
                "UPDATE outbox_events SET available_at=:at WHERE event_id=:id",
                at=updated["next_attempt_at"],
                id=event.bytes,
            )
        else:
            await cycle_failed(conn, monitor, error)
    return True
