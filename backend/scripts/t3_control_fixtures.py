"""显式隔离库内的合成在途运行；不调用学校、不运行采集或发信。"""

from dataclasses import replace
from uuid import UUID

from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.fences import Execution
from services.monitoring.repository import lock_monitor


async def running(engine, owner):
    run_id, binding, credential = new_id(), new_id(), new_id()
    async with engine.begin() as conn:
        monitor = await lock_monitor(conn, owner)
        await execute(
            conn,
            "UPDATE monitors SET desired_enabled=1,state='active',credential_allowed=1,"
            "credential_ref=:credential,credential_version=1,binding_id=:binding,"
            "next_run_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 60 MINUTE) WHERE id=:id",
            id=monitor["id"],
            credential=credential.bytes,
            binding=binding.bytes,
        )
        await execute(
            conn,
            "INSERT INTO monitor_runs (id,monitor_id,generation,scheduled_for,binding_id,"
            "credential_version,state,version,attempt_count,execution_epoch,lease_owner,lease_until,"
            "started_at) VALUES (:id,:monitor,:generation,UTC_TIMESTAMP(6),"
            ":binding,1,'running',1,1,1,"
            "'synthetic-worker',DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 45 SECOND),UTC_TIMESTAMP(6))",
            id=run_id.bytes,
            monitor=monitor["id"],
            generation=monitor["generation"],
            binding=binding.bytes,
        )
        await execute(
            conn,
            "UPDATE monitors SET active_run_id=:run WHERE id=:id",
            id=monitor["id"],
            run=run_id.bytes,
        )
    return Execution(
        UUID(bytes=monitor["id"]), run_id, monitor["generation"], binding, 1, 1, "synthetic-worker"
    ), credential


async def write_sample(conn, execution, owner):
    await execute(
        conn,
        "INSERT INTO monitor_samples (id,run_id,monitor_id,owner_user_id,binding_id,"
        "captured_at,balance,quality,credential_version) VALUES "
        "(:id,:run,:monitor,:owner,:binding,UTC_TIMESTAMP(6),10.00,'balance_only',1)",
        id=new_id().bytes,
        run=execution.run_id.bytes,
        monitor=execution.monitor_id.bytes,
        owner=owner.bytes,
        binding=execution.binding_id.bytes,
    )


async def assert_no_sample(engine, run_id):
    async with engine.connect() as conn:
        count = await first(
            conn, "SELECT COUNT(*) AS n FROM monitor_samples WHERE run_id=:id", id=run_id.bytes
        )
    assert count["n"] == 0


def invalid_executions(execution):
    return [
        replace(execution, generation=execution.generation + 1),
        replace(execution, binding_id=new_id()),
        replace(execution, credential_version=2),
        replace(execution, execution_epoch=2),
        replace(execution, lease_owner="another-worker"),
    ]
