"""MySQL 持久逻辑槽；多 Scheduler 合并到一个有效 run。"""

import hashlib
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from services.common.archive_store import request_key, unavailable
from services.common.database import OUTBOX_PENDING
from services.common.errors import ErrorCode
from services.common.events import RunReadyPayload
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.outbox import append_event
from services.common.sql import aware, execute, first

from .repository import lock_monitor
from .run_admission import check_budget, record_request


def latest_slot(anchor, now, minutes):
    interval = timedelta(minutes=minutes)
    slot = anchor + max(0, (now - anchor) // interval) * interval
    return slot, slot + interval


async def wake(conn, run, request_id, *, marker=None):
    clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
    event = marker or new_id()
    envelope = EventEnvelope(
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
    )
    if marker:
        # 首个到期 run 的合法唤醒同时作为本小时续批标记；并行 Scheduler 共用同一主键。
        await execute(
            conn,
            "INSERT INTO outbox_events (event_id,type,schema_version,aggregate_id,"
            "aggregate_version,payload,available_at,publish_attempts) "
            "VALUES (:id,:type,:schema,:aggregate,:version,:payload,UTC_TIMESTAMP(6),0) "
            "ON DUPLICATE KEY UPDATE event_id=event_id",
            id=event.bytes, type=envelope.type, schema=envelope.schema_version,
            aggregate=envelope.aggregate_id.bytes, version=envelope.aggregate_version,
            payload=envelope.model_dump_json(),
        )
        conn.info[OUTBOX_PENDING] = True
    else:
        await append_event(conn, envelope)
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


async def scheduler_tick(engine, *, proxy_enabled=False):
    async with engine.begin() as conn:
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        now = clock["now"]
        local_hour = aware(now).astimezone(ZoneInfo("Asia/Shanghai")).hour
        if local_hour >= 23 or local_hour < 6:
            return False
        trigger, marker = None, None
        eligible = (
            "SELECT * FROM monitors WHERE state='active' AND desired_enabled=1 "
            "AND credential_allowed=1 AND credential_operation_id IS NULL "
        )
        if proxy_enabled:
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)
            marker = uuid5(NAMESPACE_URL, f"elect:monitoring:proxy-hour:{hour_start.isoformat()}")
            started = await first(
                conn, "SELECT event_id FROM outbox_events WHERE event_id=:id", id=marker.bytes
            )
            if not started:
                trigger = await first(
                    conn, eligible + "AND next_run_at<=:now ORDER BY next_run_at,id "
                    "LIMIT 1 FOR UPDATE SKIP LOCKED", now=now,
                )
                if not trigger:
                    return False
            condition = "AND next_run_at<:end "
            params = {"end": hour_end, "limit": 100 - bool(trigger)}
            if trigger:
                condition += "AND id<>:trigger "
                params["trigger"] = trigger["id"]
        else:
            condition = "AND next_run_at<=UTC_TIMESTAMP(6) "
            params = {"limit": 100}
        monitors = (
            (
                await execute(
                    conn, eligible + condition + "ORDER BY next_run_at,id "
                    "LIMIT :limit FOR UPDATE SKIP LOCKED", **params,
                )
            )
            .mappings()
            .all()
        )
        if trigger:
            monitors.insert(0, trigger)
        for monitor in monitors:
            anchor = monitor["schedule_anchor_at"] or monitor["next_run_at"]
            if proxy_enabled and monitor["next_run_at"] > now:
                slot = monitor["next_run_at"]
                following = slot + timedelta(minutes=monitor["interval_minutes"])
            else:
                cutoff = hour_end - timedelta(microseconds=1) if proxy_enabled else now
                slot, following = latest_slot(anchor, cutoff, monitor["interval_minutes"])
            run = await create_run(conn, monitor, slot, new_id())
            if trigger and monitor["id"] == trigger["id"]:
                await wake(conn, run, new_id(), marker=marker)
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
    digest = hashlib.sha256(b"manual_run").digest()
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
        cold = await request_key(conn, owner, "manual_run", key_hash, digest)
        if cold:
            result = await first(conn, "SELECT r.* FROM monitor_runs r JOIN monitors m "
                "ON m.id=r.monitor_id WHERE r.id=:id AND m.owner_user_id=:owner",
                id=cold, owner=owner.bytes)
            if not result:
                raise unavailable()
            return result
        await check_budget(conn, owner)
        if (
            monitor["state"] != "active"
            or not monitor["desired_enabled"]
            or not monitor["credential_allowed"]
            or monitor["credential_operation_id"]
        ):
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "请先启用有效默认寝室的监控")
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        row = await create_run(conn, monitor, clock["now"], request_id)
        await record_request(conn, owner, key_hash, row["id"])
        return row
