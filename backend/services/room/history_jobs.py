"""C02 分段同步受理；请求内容和窗口进度持久保存。"""

import hashlib
from functools import partial

from services.common.dates import check_range, windows
from services.common.events import HistorySyncPayload
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.outbox import append_event
from services.common.sql import aware, execute, first

from .history_admission import check_admission, covering_sync
from .query_jobs import accept_query


async def accept_history(engine, owner, binding, command, key, request_id):
    check_range(command.start_date, command.end_date)
    digest = hashlib.sha256(
        f"history:{binding}:{command.start_date}:{command.end_date}".encode()
    ).digest()
    async with engine.begin() as conn:
        operation, created = await accept_query(
            conn, owner, binding, key, "history_sync", digest,
            admission=partial(check_admission, owner=owner, binding=binding, command=command),
        )
        if not created:
            return operation
        pending = await covering_sync(conn, owner, binding, command)
        if pending:
            await execute(
                conn,
                "UPDATE room_operations SET "
                "saga_step='merged',upstream_operation_id=:prior WHERE id=:id",
                id=operation.bytes,
                prior=pending["operation_id"],
            )
            return operation
        sync = new_id()
        await execute(
            conn,
            "INSERT INTO history_syncs "
            "(id,owner_user_id,binding_id,operation_id,requested_start,requested_end,s"
            "ource,status,coverage,version) VALUES "
            "(:id,:owner,:binding,:op,:start,:end,'C02','accepted','unknown',1)",
            id=sync.bytes,
            owner=owner.bytes,
            binding=binding.bytes,
            op=operation.bytes,
            start=command.start_date,
            end=command.end_date,
        )
        for start, end in windows(command.start_date, command.end_date):
            await execute(
                conn,
                "INSERT INTO history_sync_windows "
                "(id,sync_id,start_date,end_date,state,attempt_count,next_attempt_at,e"
                "xecution_epoch) VALUES "
                "(:id,:sync,:start,:end,'pending',0,UTC_TIMESTAMP(6),1)",
                id=new_id().bytes,
                sync=sync.bytes,
                start=start,
                end=end,
            )
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        await append_event(
            conn,
            EventEnvelope(
                event_id=new_id(),
                type="room.history_sync_requested",
                schema_version=1,
                producer="room",
                aggregate_id=sync,
                aggregate_version=1,
                occurred_at=aware(clock["now"]),
                request_id=request_id,
                payload=HistorySyncPayload(sync_id=sync, binding_id=binding),
                dedupe_key=str(sync),
            ),
        )
    return operation


async def claim_history(engine, schedule=None, *, stop=None):
    from .history_execution import LEASE_SECONDS
    from .read_claims import HISTORY_DUE, candidates, lock_idle

    for owner in await candidates(engine, "history_sync", schedule):
        if stop and stop.is_set():
            return None
        if schedule:
            schedule.visited("history_sync", owner)
        async with engine.begin() as conn:
            if not await lock_idle(conn, owner):
                continue
            row = await first(
                conn,
                "SELECT w.*,s.owner_user_id,s.binding_id,s.operation_id,"
                "UTC_TIMESTAMP(6) AS claimed_at FROM "
                "history_sync_windows w JOIN history_syncs s ON s.id=w.sync_id WHERE "
                "s.owner_user_id=:owner AND " + HISTORY_DUE + " ORDER BY "
                "s.created_at,w.start_date,w.id LIMIT 1 FOR UPDATE",
                owner=owner,
            )
            if not row or stop and stop.is_set():
                continue
            lease = str(new_id())
            if row["attempt_count"] >= 3:
                from .history_store import finish_sync

                await execute(
                    conn,
                    "UPDATE history_sync_windows SET "
                    "state='failed',lease_owner=NULL,lease_until=NULL,error_code='SCHO"
                    "OL_TIMEOUT' WHERE id=:id",
                    id=row["id"],
                )
                await finish_sync(conn, row)
                continue
            await execute(
                conn,
                "UPDATE history_sync_windows SET "
                "state='running',attempt_count=attempt_count+1,execution_epoch=executi"
                "on_epoch+1,lease_owner=:lease,lease_until=TIMESTAMPADD(SECOND,:seconds,"
                "UTC_TIMESTAMP(6)) WHERE id=:id",
                id=row["id"],
                lease=lease,
                seconds=LEASE_SECONDS,
            )
            await execute(
                conn, "UPDATE history_syncs SET status='running' WHERE id=:id", id=row["sync_id"]
            )
            await execute(
                conn,
                "UPDATE room_operations SET state='running' WHERE id=:id",
                id=row["operation_id"],
            )
            from services.common.read_schedule import claimed

            claimed("room", "history_sync", row, row["next_attempt_at"])
            return {
                **row,
                "lease_owner": lease,
                "attempt_count": row["attempt_count"] + 1,
                "execution_epoch": row["execution_epoch"] + 1,
            }
    return None
