"""执行结果的事务屏障；验证与调用者的结果写入共享同一事务和行锁。"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import first


@dataclass(frozen=True)
class Execution:
    monitor_id: UUID
    run_id: UUID
    generation: int
    binding_id: UUID
    credential_version: int
    execution_epoch: int
    lease_owner: str


def valid_execution(monitor, run, execution, now):
    return bool(
        monitor
        and run
        and monitor["id"] == execution.monitor_id.bytes
        and run["monitor_id"] == monitor["id"]
        and monitor["active_run_id"] == run["id"]
        and monitor["desired_enabled"]
        and monitor["state"] == "active"
        and monitor["credential_allowed"]
        and not monitor["credential_operation_id"]
        and run["id"] == execution.run_id.bytes
        and run["state"] == "running"
        and monitor["generation"] == run["generation"] == execution.generation
        and monitor["binding_id"] == run["binding_id"] == execution.binding_id.bytes
        and monitor["credential_version"]
        == run["credential_version"]
        == execution.credential_version
        and run["execution_epoch"] == execution.execution_epoch
        and run["lease_owner"] == execution.lease_owner
        and run["lease_until"]
        and run["lease_until"] > now
        and run["cancel_requested_at"] is None
    )


@asynccontextmanager
async def fenced_transaction(engine, execution):
    async with engine.begin() as conn:
        monitor = await first(
            conn, "SELECT * FROM monitors WHERE id=:id FOR UPDATE", id=execution.monitor_id.bytes
        )
        run = await first(
            conn,
            "SELECT * FROM monitor_runs WHERE id=:id AND monitor_id=:monitor FOR UPDATE",
            id=execution.run_id.bytes,
            monitor=execution.monitor_id.bytes,
        )
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        if not valid_execution(monitor, run, execution, clock["now"]):
            raise ApiError(409, ErrorCode.VERSION_CONFLICT, "运行已失效，结果不可提交")
        yield conn, monitor, run
