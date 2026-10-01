"""默认和绑定任务的持久租约；迟到 Worker 不能推进本域操作。"""

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .preference_store import locked_operation


async def claim(engine):
    async with engine.begin() as conn:
        row = await first(
            conn,
            "SELECT * FROM room_operations WHERE type IN ('switch_default','bind_room',"
            "'unbind_room') "
            "AND (state IN ('accepted','running','reconciling','unknown') OR (state='failed' "
            "AND saga_step='compensating')) "
            "AND next_reconcile_at<=UTC_TIMESTAMP(6) "
            "AND (lease_until IS NULL OR lease_until<=UTC_TIMESTAMP(6)) "
            "ORDER BY next_reconcile_at,id LIMIT 1 FOR UPDATE SKIP LOCKED",
        )
        if not row:
            return None
        lease = str(new_id())
        await execute(
            conn,
            "UPDATE room_operations SET "
            "state=IF(state='accepted','running',state),lease_owner=:lease,"
            "lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 120 "
            "SECOND),updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            lease=lease,
            id=row["id"],
        )
        return {**row, "lease_owner": lease}


async def update(
    engine,
    row,
    *,
    step=None,
    error=None,
    state="running",
    done=False,
    release=False,
    delay=5,
    binding_status=None,
):
    async with engine.begin() as conn:
        current = await locked_operation(conn, row)
        if not current:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "操作租约已变化")
        await execute(
            conn,
            "UPDATE room_operations SET state=:state,saga_step=:step,error_code=:error,"
            "binding_status=COALESCE(:binding_status,binding_status),"
            "next_reconcile_at=IF(:done,NULL,TIMESTAMPADD(SECOND,:delay,UTC_TIMESTAMP(6))),"
            "lease_owner=IF(:release,NULL,lease_owner),"
            "lease_until=IF(:release,NULL,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 120 SECOND)),"
            "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=row["id"],
            state=state,
            step=step or current["saga_step"],
            error=error,
            done=done,
            delay=delay,
            binding_status=binding_status,
            release=release or done,
        )
