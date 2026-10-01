"""历史成功范围快照替换及租约栅栏；失败不覆盖旧记录。"""

import random
from collections import Counter

from services.common.ids import new_id
from services.common.sql import execute, first


async def finish_sync(conn, row):
    counts = await first(
        conn,
        "SELECT SUM(state IN ('pending','running','retry_wait')) AS "
        "pending,SUM(state='failed') AS failed FROM history_sync_windows WHERE "
        "sync_id=:id",
        id=row["sync_id"],
    )
    known = await first(
        conn,
        "SELECT COUNT(*) AS n FROM school_history_records WHERE binding_id=:binding "
        "AND source='C02'",
        binding=row["binding_id"],
    )
    state = "running" if counts["pending"] else "failed" if counts["failed"] else "succeeded"
    error = await first(
        conn,
        "SELECT error_code FROM history_sync_windows WHERE sync_id=:id AND state='failed' LIMIT 1",
        id=row["sync_id"],
    )
    code = error["error_code"] if error else None
    await execute(
        conn,
        "UPDATE history_syncs SET "
        "status=:state,coverage=:coverage,error_code=:error,version=version+1,fetched_"
        "at=UTC_TIMESTAMP(6),updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
        id=row["sync_id"],
        state=state,
        coverage="partial" if known["n"] else "unknown",
        error=code,
    )
    await execute(
        conn,
        "UPDATE room_operations SET "
        "state=:state,error_code=:error,saga_step=IF(:state='running','read_school','c"
        "omplete'),next_reconcile_at=IF(:state='running',UTC_TIMESTAMP(6),NULL),update"
        "d_at=UTC_TIMESTAMP(6) WHERE id=:op OR (upstream_operation_id=:op AND "
        "type='history_sync' AND saga_step='merged')",
        op=row["operation_id"],
        state=state,
        error=code,
    )


async def finish_history(engine, row, result, error, retryable=False):
    from uuid import UUID

    from .preference_store import lock_preference
    from .query_jobs import target

    async with engine.begin() as conn:
        await lock_preference(conn, UUID(bytes=row["owner_user_id"]))
        current = await first(
            conn,
            "SELECT *,lease_until>UTC_TIMESTAMP(6) AS valid FROM history_sync_windows "
            "WHERE id=:id FOR UPDATE",
            id=row["id"],
        )
        if (
            current["state"] != "running"
            or current["lease_owner"] != row["lease_owner"]
            or current["execution_epoch"] != row["execution_epoch"]
            or not current["valid"]
        ):
            return False
        binding = await target(
            conn, UUID(bytes=row["owner_user_id"]), UUID(bytes=row["binding_id"])
        )
        if binding["status"] != "active":
            error, retryable = "NOT_FOUND", False
        if error:
            retry = retryable and current["attempt_count"] < 3
            delay = (30 if current["attempt_count"] == 1 else 120) + random.uniform(0, 5)
            await execute(
                conn,
                "UPDATE history_sync_windows SET "
                "state=:state,error_code=:error,next_attempt_at=IF(:retry,TIMESTAMPADD"
                "(SECOND,:delay,UTC_TIMESTAMP(6)),NULL),lease_owner=NULL,lease_until=N"
                "ULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=row["id"],
                state="retry_wait" if retry else "failed",
                error=error,
                retry=retry,
                delay=delay,
            )
        else:
            # 同账号串行窗口，成功批次仅替换其请求日期；同日多行不按日期唯一化。
            await execute(
                conn,
                "DELETE FROM school_history_records WHERE binding_id=:id AND "
                "source='C02' AND record_date BETWEEN :start AND :end",
                id=row["binding_id"],
                start=row["start_date"],
                end=row["end_date"],
            )
            occurrences = Counter()
            for record in result["items"]:
                fingerprint = bytes.fromhex(record["row_hash"])
                occurrences[fingerprint] += 1
                await execute(
                    conn,
                    "INSERT INTO school_history_records "
                    "(id,binding_id,request_room_id,source,record_date,source_timezone"
                    ",last_reading,reading,energy_usage,charged_amount,charge_status,r"
                    "ow_hash,sync_id,occurrence_index,snapshot_version,quality) "
                    "VALUES "
                    "(:id,:binding,:room,'C02',:date,'Asia/Shanghai',:last,:reading,:u"
                    "sage,:amount,:status,:hash,:sync,:occurrence,:version,:quality)",
                    id=new_id().bytes,
                    binding=row["binding_id"],
                    room=result["request_room_id"],
                    date=record["record_date"],
                    last=record["last_reading"],
                    reading=record["reading"],
                    usage=record["energy_usage"],
                    amount=record["charged_amount"],
                    status=record["charge_status"],
                    hash=fingerprint,
                    sync=row["sync_id"],
                    occurrence=occurrences[fingerprint],
                    version=current["execution_epoch"],
                    quality=record["quality"],
                )
            await execute(
                conn,
                "UPDATE history_sync_windows SET "
                "state='succeeded',error_code=NULL,next_attempt_at=NULL,lease_owner=NU"
                "LL,lease_until=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=row["id"],
            )
        await finish_sync(conn, row)
    return True
