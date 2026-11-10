"""小时合批使用隔离 MySQL 和合成监控，不访问学校或业务环境。"""

import asyncio
import json
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from query_resource_support import database, requires_mysql
from sqlalchemy import text

from services.common.ids import new_id
from services.common.sql import execute
from services.monitoring import scheduler

pytestmark = requires_mysql
NOW = datetime(2026, 1, 1, 15, 10)  # 北京时间 23:10，跨日边界也是 UTC 整点。


def use_clock(monkeypatch):
    real_first = scheduler.first

    async def fixed_first(conn, statement, **params):
        if statement == "SELECT UTC_TIMESTAMP(6) AS now":
            return {"now": NOW}
        return await real_first(conn, statement, **params)

    monkeypatch.setattr(scheduler, "first", fixed_first)


async def seed(engine, specs):
    rows = []
    for spec in specs:
        owner, binding = new_id(), new_id()
        rows.append({
            "id": new_id().bytes, "owner": owner.bytes, "binding": binding.bytes,
            "next": spec["next"], "anchor": spec.get("anchor", spec["next"]),
            "interval": spec.get("interval", 60), "allowed": spec.get("allowed", True),
            "operation": spec.get("operation"),
        })
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO monitors (id,owner_user_id,binding_id,credential_ref,credential_version,"
            "desired_enabled,state,health,interval_minutes,repeat_limit,threshold,email_version,"
            "version,generation,consecutive_failures,credential_allowed,credential_operation_id,"
            "schedule_anchor_at,next_run_at) VALUES (:id,:owner,:binding,:binding,1,1,'active',"
            "'healthy',:interval,2,20,1,1,1,0,:allowed,:operation,:anchor,:next)"
        ), rows)
    return rows


async def status(engine):
    async with engine.connect() as conn:
        monitors = (await execute(conn, "SELECT * FROM monitors ORDER BY id")).mappings().all()
        runs = (await execute(conn, "SELECT * FROM monitor_runs ORDER BY id")).mappings().all()
        events = (await execute(conn, "SELECT * FROM outbox_events ORDER BY event_id"))
        events = events.mappings().all()
    return {row["id"]: row for row in monitors}, runs, events


def test_no_due_or_manual_run_does_not_start_batch(monkeypatch):
    use_clock(monkeypatch)

    async def case():
        async with database("monitoring") as engine:
            rows = await seed(engine, [
                {"next": NOW + timedelta(minutes=20)},
                {"next": NOW + timedelta(minutes=30)},
            ])
            assert not await scheduler.scheduler_tick(engine, proxy_enabled=True)
            manual = await scheduler.accept_run(engine, UUID(bytes=rows[0]["owner"]),
                                                str(new_id()), new_id())
            assert not await scheduler.scheduler_tick(engine, proxy_enabled=True)
            monitors, runs, events = await status(engine)
            assert len(runs) == 1 and runs[0]["id"] == manual["id"] and len(events) == 1
            assert [monitors[row["id"]]["next_run_at"] for row in rows] == [
                row["next"] for row in rows
            ]

    asyncio.run(case())


def test_hour_boundary_and_next_slot_remain_anchored(monkeypatch):
    use_clock(monkeypatch)

    async def case():
        async with database("monitoring") as engine:
            hour_end = NOW.replace(minute=0) + timedelta(hours=1)
            anchor = NOW - timedelta(hours=4, minutes=3)
            rows = await seed(engine, [
                {"next": anchor + timedelta(hours=2), "anchor": anchor},
                {"next": hour_end - timedelta(microseconds=1),
                 "anchor": hour_end - timedelta(minutes=75, microseconds=1), "interval": 75},
                {"next": hour_end},
                {"next": NOW + timedelta(minutes=1), "allowed": False},
                {"next": NOW + timedelta(minutes=1), "operation": new_id().bytes},
            ])
            assert await scheduler.scheduler_tick(engine, proxy_enabled=True)
            monitors, runs, events = await status(engine)
            by_monitor = {run["monitor_id"]: run for run in runs}
            assert set(by_monitor) == {rows[0]["id"], rows[1]["id"]}
            assert by_monitor[rows[0]["id"]]["scheduled_for"] == NOW - timedelta(minutes=3)
            assert monitors[rows[0]["id"]]["next_run_at"] == NOW + timedelta(minutes=57)
            assert by_monitor[rows[1]["id"]]["scheduled_for"] == rows[1]["next"]
            assert monitors[rows[1]["id"]]["next_run_at"] == rows[1]["next"] + timedelta(minutes=75)
            assert all(monitors[row["id"]]["schedule_anchor_at"] == row["anchor"] for row in rows)
            assert all(monitors[row["id"]]["next_run_at"] == row["next"] for row in rows[2:])
            marker = uuid5(NAMESPACE_URL, "elect:monitoring:proxy-hour:2026-01-01T15:00:00")
            marked = next(event for event in events if event["event_id"] == marker.bytes)
            payload = json.loads(marked["payload"])
            assert payload["type"] == "monitor.run_ready"
            assert payload["payload"]["run_id"] == str(UUID(bytes=by_monitor[rows[0]["id"]]["id"]))

    asyncio.run(case())


def test_overdue_slots_do_not_repeat_after_the_run_finishes(monkeypatch):
    use_clock(monkeypatch)

    async def case():
        async with database("monitoring") as engine:
            anchor = NOW - timedelta(minutes=50)
            long_anchor = NOW - timedelta(hours=1, minutes=20)
            rows = await seed(engine, [
                {"next": anchor},
                {"next": long_anchor, "interval": 180},
            ])
            assert await scheduler.scheduler_tick(engine, proxy_enabled=True)
            monitors, runs, _ = await status(engine)
            by_monitor = {run["monitor_id"]: run for run in runs}
            assert by_monitor[rows[0]["id"]]["scheduled_for"] == anchor + timedelta(hours=1)
            assert monitors[rows[0]["id"]]["next_run_at"] == anchor + timedelta(hours=2)
            assert by_monitor[rows[1]["id"]]["scheduled_for"] == long_anchor
            assert monitors[rows[1]["id"]]["next_run_at"] == long_anchor + timedelta(hours=3)
            assert all(monitors[row["id"]]["schedule_anchor_at"] == row["anchor"] for row in rows)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE monitor_runs SET state='succeeded',"
                              "finished_at=UTC_TIMESTAMP(6)")
                await execute(conn, "UPDATE monitors SET active_run_id=NULL")
            assert not await scheduler.scheduler_tick(engine, proxy_enabled=True)
            after, runs, _ = await status(engine)
            assert len(runs) == 2
            assert all(after[row["id"]]["next_run_at"] == monitors[row["id"]]["next_run_at"]
                       for row in rows)

    asyncio.run(case())


def test_hour_batch_continues_beyond_100_with_a_merged_manual_run(monkeypatch):
    use_clock(monkeypatch)

    async def case():
        async with database("monitoring") as engine:
            rows = await seed(engine, [{"next": NOW - timedelta(minutes=1)}] + [
                {"next": NOW + timedelta(minutes=20)} for _ in range(105)
            ])
            manual = await scheduler.accept_run(engine, UUID(bytes=rows[0]["owner"]),
                                                str(new_id()), new_id())
            assert await scheduler.scheduler_tick(engine, proxy_enabled=True)
            monitors, runs, events = await status(engine)
            assert len(runs) == 100
            assert sum(monitors[row["id"]]["next_run_at"] == row["next"] for row in rows) == 6
            marker = uuid5(NAMESPACE_URL, "elect:monitoring:proxy-hour:2026-01-01T15:00:00")
            marked = next(event for event in events if event["event_id"] == marker.bytes)
            assert json.loads(marked["payload"])["payload"]["run_id"] == str(
                UUID(bytes=manual["id"])
            )
            assert await scheduler.scheduler_tick(engine, proxy_enabled=True)
            monitors, runs, _ = await status(engine)
            assert len(runs) == 106
            assert all(monitors[row["id"]]["next_run_at"] > row["next"] for row in rows)
            assert not await scheduler.scheduler_tick(engine, proxy_enabled=True)

    asyncio.run(case())


def test_two_schedulers_share_the_hour_marker(monkeypatch):
    use_clock(monkeypatch)
    real_first = scheduler.first
    both_locked = asyncio.Event()
    trigger_count = 0

    async def synchronize_triggers(conn, statement, **params):
        nonlocal trigger_count
        row = await real_first(conn, statement, **params)
        if "LIMIT 1 FOR UPDATE SKIP LOCKED" in statement and row:
            trigger_count += 1
            if trigger_count == 2:
                both_locked.set()
            await asyncio.wait_for(both_locked.wait(), timeout=5)
        return row

    monkeypatch.setattr(scheduler, "first", synchronize_triggers)

    async def case():
        async with database("monitoring") as engine:
            rows = await seed(engine, [{"next": NOW - timedelta(minutes=1)}] * 2 + [
                {"next": NOW + timedelta(minutes=20)} for _ in range(10)
            ])
            assert all(await asyncio.gather(
                scheduler.scheduler_tick(engine, proxy_enabled=True),
                scheduler.scheduler_tick(engine, proxy_enabled=True),
            ))
            monitors, runs, events = await status(engine)
            assert {run["monitor_id"] for run in runs} == {row["id"] for row in rows}
            assert all(monitors[row["id"]]["next_run_at"] > row["next"] for row in rows)
            marker = uuid5(NAMESPACE_URL, "elect:monitoring:proxy-hour:2026-01-01T15:00:00")
            assert sum(event["event_id"] == marker.bytes for event in events) == 1

    asyncio.run(case())


def test_without_proxy_only_due_monitor_is_scheduled():
    async def case():
        async with database("monitoring") as engine:
            rows = await seed(engine, [
                {"next": NOW - timedelta(minutes=1)},
                {"next": NOW + timedelta(minutes=10)},
            ])
            # 非代理查询仍使用数据库真实时钟；将两条计划等距平移到真实时间附近。
            async with engine.begin() as conn:
                await execute(conn, "UPDATE monitors SET schedule_anchor_at="
                              "DATE_ADD(UTC_TIMESTAMP(6), INTERVAL IF(id=:due,-1,10) MINUTE),"
                              "next_run_at=DATE_ADD(UTC_TIMESTAMP(6),"
                              "INTERVAL IF(id=:due,-1,10) MINUTE)", due=rows[0]["id"])
            assert await scheduler.scheduler_tick(engine)
            _, runs, _ = await status(engine)
            assert len(runs) == 1 and runs[0]["monitor_id"] == rows[0]["id"]

    asyncio.run(case())
