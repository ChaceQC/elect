"""短租约领取与续租；所有事务按 monitor → run 加锁。"""

from uuid import UUID

from services.common.ids import new_id
from services.common.sql import execute, first

from .fences import Execution, valid_execution


def execution_of(run, worker):
    return Execution(
        monitor_id=UUID(bytes=run["monitor_id"]),
        run_id=UUID(bytes=run["id"]),
        generation=run["generation"],
        binding_id=UUID(bytes=run["binding_id"]),
        credential_version=run["credential_version"],
        execution_epoch=run["execution_epoch"],
        lease_owner=worker,
    )


async def claim_run(engine, run_id=None):
    worker = str(new_id())
    async with engine.begin() as conn:
        params = {"run": run_id.bytes if run_id else None}
        monitor = await first(
            conn,
            "SELECT * FROM monitors WHERE state='active' AND desired_enabled=1 "
            "AND credential_allowed=1 AND credential_operation_id IS NULL AND active_run_id IN "
            "(SELECT id FROM monitor_runs WHERE state IN ('pending','retry_wait') "
            "AND next_attempt_at<=UTC_TIMESTAMP(6) AND (:run IS NULL OR id=:run)) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED",
            **params,
        )
        if not monitor:
            return None
        run = await first(
            conn, "SELECT * FROM monitor_runs WHERE id=:id FOR UPDATE", id=monitor["active_run_id"]
        )
        if (
            run["generation"] != monitor["generation"]
            or run["binding_id"] != monitor["binding_id"]
            or run["credential_version"] != monitor["credential_version"]
            or run["attempt_count"] >= 3
        ):
            return None
        await execute(
            conn,
            "UPDATE monitor_runs SET state='running',attempt_count=attempt_count+1,"
            "version=version+1,execution_epoch=execution_epoch+1,lease_owner=:worker,"
            "lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 45 SECOND),"
            "started_at=COALESCE(started_at,UTC_TIMESTAMP(6)),next_attempt_at=NULL "
            "WHERE id=:id",
            id=run["id"],
            worker=worker,
        )
        run = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=run["id"])
        await execute(
            conn,
            "INSERT INTO monitor_attempts (id,run_id,attempt_no,worker_id,execution_epoch,"
            "started_at,outcome) VALUES (:id,:run,:attempt,:worker,:epoch,UTC_TIMESTAMP(6),"
            "'running')",
            id=new_id().bytes,
            run=run["id"],
            attempt=run["attempt_count"],
            worker=worker,
            epoch=run["execution_epoch"],
        )
        return execution_of(run, worker)


async def renew(engine, execution):
    async with engine.begin() as conn:
        monitor = await first(
            conn, "SELECT * FROM monitors WHERE id=:id FOR UPDATE", id=execution.monitor_id.bytes
        )
        run = await first(
            conn, "SELECT * FROM monitor_runs WHERE id=:id FOR UPDATE", id=execution.run_id.bytes
        )
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        attempt = await first(
            conn,
            "SELECT started_at FROM monitor_attempts WHERE run_id=:id AND execution_epoch=:epoch",
            id=execution.run_id.bytes,
            epoch=execution.execution_epoch,
        )
        if (
            not valid_execution(monitor, run, execution, clock["now"])
            or not attempt
            or (clock["now"] - attempt["started_at"]).total_seconds() >= 90
        ):
            return False
        await execute(
            conn,
            "UPDATE monitor_runs SET lease_until=LEAST(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL "
            "45 SECOND),TIMESTAMPADD(SECOND,90,:started)) WHERE id=:id",
            id=run["id"],
            started=attempt["started_at"],
        )
        return True
