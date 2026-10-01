"""MySQL 持久逻辑槽；多 Scheduler 合并到一个有效 run。"""

import hashlib
from datetime import timedelta
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.events import RunReadyPayload
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.outbox import append_event
from services.common.sql import aware, execute, first

from .repository import lock_monitor


def latest_slot(anchor, now, minutes):
    interval = timedelta(minutes=minutes)
    slot = anchor + max(0, (now - anchor) // interval) * interval
    return slot, slot + interval


async def wake(conn, run, request_id):
    clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
    event = new_id()
    await append_event(
        conn,
        EventEnvelope(
            event_id=event,
            type="monitor.run_ready",
            schema_version=1,
            producer="monitoring",
            aggregate_id=UUID(bytes=run["monitor_id"]),
            aggregate_version=run["generation"],
            occurred_at=aware(clock["now"]),
            request_id=request_id,
            payload=RunReadyPayload(run_id=UUID(bytes=run["id"]), generation=run["generation"]),
            dedupe_key=str(event),
        ),
    )
    return event


async def create_run(conn, monitor, scheduled, request_id):
    active = (
        await first(
            conn, "SELECT * FROM monitor_runs WHERE id=:id FOR UPDATE", id=monitor["active_run_id"]
        )
        if monitor["active_run_id"]
        else None
    )
    if (
        active
        and active["state"] in {"pending", "running", "retry_wait"}
        and active["generation"] == monitor["generation"]
    ):
        return active
    prior = await first(
        conn,
        "SELECT * FROM monitor_runs WHERE monitor_id=:monitor AND generation=:generation "
        "AND scheduled_for=:scheduled",
        monitor=monitor["id"],
        generation=monitor["generation"],
        scheduled=scheduled,
    )
    if prior:
        return prior
    run_id = new_id()
    await execute(
        conn,
        "INSERT INTO monitor_runs (id,monitor_id,generation,scheduled_for,binding_id,"
        "credential_version,state,version,attempt_count,next_attempt_at,execution_epoch) "
        "VALUES (:id,:monitor,:generation,:scheduled,:binding,:credential,'pending',1,0,"
        "UTC_TIMESTAMP(6),1)",
        id=run_id.bytes,
        monitor=monitor["id"],
        generation=monitor["generation"],
        scheduled=scheduled,
        binding=monitor["binding_id"],
        credential=monitor["credential_version"],
    )
    await execute(
        conn,
        "UPDATE monitors SET active_run_id=:run WHERE id=:id",
        id=monitor["id"],
        run=run_id.bytes,
    )
    row = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=run_id.bytes)
    await wake(conn, row, request_id)
    return row


async def scheduler_tick(engine):
    async with engine.begin() as conn:
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        monitors = (
            (
                await execute(
                    conn,
                    "SELECT * FROM monitors WHERE state='active' AND desired_enabled=1 "
                    "AND credential_allowed=1 AND credential_operation_id IS NULL "
                    "AND next_run_at<=UTC_TIMESTAMP(6) ORDER BY next_run_at,id "
                    "LIMIT 100 FOR UPDATE SKIP LOCKED",
                )
            )
            .mappings()
            .all()
        )
        for monitor in monitors:
            anchor = monitor["schedule_anchor_at"] or monitor["next_run_at"]
            slot, following = latest_slot(anchor, clock["now"], monitor["interval_minutes"])
            await create_run(conn, monitor, slot, new_id())
            await execute(
                conn,
                "UPDATE monitors SET schedule_anchor_at=:anchor,next_run_at=:next WHERE id=:id",
                id=monitor["id"],
                anchor=anchor,
                next=following,
            )
    return bool(monitors)


async def accept_run(engine, owner, key, request_id):
    key_hash = hashlib.sha256(key.encode()).digest()
    async with engine.begin() as conn:
        monitor = await lock_monitor(conn, owner)
        prior = await first(
            conn,
            "SELECT r.* FROM monitor_run_requests q JOIN monitor_runs r ON r.id=q.run_id "
            "WHERE q.owner_user_id=:owner AND q.idempotency_key_hash=:key",
            owner=owner.bytes,
            key=key_hash,
        )
        if prior:
            return prior
        if (
            monitor["state"] != "active"
            or not monitor["desired_enabled"]
            or not monitor["credential_allowed"]
            or monitor["credential_operation_id"]
        ):
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "请先启用有效默认寝室的监控")
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        row = await create_run(conn, monitor, clock["now"], request_id)
        await execute(
            conn,
            "INSERT INTO monitor_run_requests (owner_user_id,idempotency_key_hash,request_d"
            "igest,run_id,expires_at) VALUES (:owner,:key,:digest,:run,DATE_ADD(UTC_TIMESTA"
            "MP(6),INTERVAL 7 DAY))",
            owner=owner.bytes,
            key=key_hash,
            digest=hashlib.sha256(b"manual_run").digest(),
            run=row["id"],
        )
        return row
