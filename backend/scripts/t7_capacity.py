"""模拟学校/实际SQL与MQ的有界单轮容量；不预测真实学校支持规模。"""

import argparse
import asyncio
import json
import os
import resource
import time
from statistics import median
from uuid import UUID

import httpx

from scripts.t2_smoke import fixture_apps
from services.common.broker import Broker, verified_event
from services.common.ids import new_id
from services.common.job import relay_tick
from services.common.outbox import consume_once
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.execution import claim_run
from services.monitoring.job import registered
from services.monitoring.repository import lock_monitor
from services.monitoring.results import succeed
from services.monitoring.scheduler import scheduler_tick


async def plans(app, count):
    ids = []
    config = MonitorConfiguration(app.state.database, app.state.email_crypto)
    for _ in range(count):
        owner = new_id()
        async with app.state.database.begin() as conn:
            monitor = await lock_monitor(conn, owner)
            await execute(
                conn, "UPDATE monitors SET binding_id=:binding,credential_ref=:credential,"
                "credential_version=1,credential_allowed=1 WHERE id=:id",
                id=monitor["id"], binding=new_id().bytes, credential=new_id().bytes,
            )
        await config.patch(owner, MonitorPatch(
            enabled=True, email="synthetic@example.invalid", expected_version=monitor["version"]
        ), new_id())
        async with app.state.database.begin() as conn:
            await execute(
                conn, "UPDATE monitors SET "
                "next_run_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 60 SECOND),"
                "schedule_anchor_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 60 SECOND) WHERE id=:id",
                id=monitor["id"],
            )
        ids.append(monitor["id"])
    return ids


async def run(apps, count, workers):
    app, adapter = apps["monitoring"], apps["school_adapter"].state
    engine, ids = app.state.database, await plans(app, count)
    params = {f"i{index}": value for index, value in enumerate(ids)}
    predicate = ",".join(f":{key}" for key in params)
    active, peak, requests = 0, 0, 0
    saturated = asyncio.Event()

    async def school(request):
        nonlocal active, peak, requests
        active += 1
        requests += 1
        peak = max(peak, active)
        if active == 4:
            saturated.set()
        try:
            await asyncio.sleep(0.03)
            return httpx.Response(200, json={"code": 200, "data": {"balance": "25.50"}})
        finally:
            active -= 1

    adapter.school_protocol.transport.transport = httpx.MockTransport(school)
    start = time.perf_counter()
    while any(await asyncio.gather(scheduler_tick(engine), scheduler_tick(engine))):
        pass
    async with engine.connect() as conn:
        rows = (await execute(
            conn, f"SELECT id FROM monitor_runs WHERE monitor_id IN ({predicate})", **params,
        )).mappings().all()
    assert len(rows) == count
    scheduling = time.perf_counter() - start
    queue = asyncio.Queue()
    for row in rows:
        queue.put_nowait(UUID(bytes=row["id"]))
    timings = []

    async def worker():
        while not queue.empty():
            run_id = queue.get_nowait()
            began = time.perf_counter()
            execution = await claim_run(engine, run_id)
            assert execution
            from services.school_adapter.infrastructure.transport import Deadline

            async with adapter.school_store.account_lock(
                f"synthetic-capacity-{execution.monitor_id}", deadline=Deadline(25)
            ):
                result = await adapter.school_protocol.read(
                    "/base/roomUser/selectRoomListByUserId", "synthetic-token", {},
                    pool="background",
                )
            await succeed(engine, execution, result["data"]["balance"], new_id())
            timings.append(time.perf_counter() - began)

    async def interactive():
        async with asyncio.timeout(10):
            await saturated.wait()
        await adapter.school_protocol.read(
            "/base/roomUser/selectRoomListByUserId", "synthetic-interactive", {}, pool="interactive"
        )

    await asyncio.gather(*(worker() for _ in range(workers)), interactive())
    capture_seconds = time.perf_counter() - start
    broker = Broker(app.state.runtime)
    await broker.open()
    message_start, known = time.perf_counter(), set()
    run_ids = {UUID(bytes=row["id"]) for row in rows}
    try:
        for _ in range(5000):
            if not await relay_tick(engine, broker):
                break
        else:
            raise AssertionError("消息发布超过有限预算")
        messages = await broker.channel.declare_queue("elect.monitoring.runs", durable=True)
        for _ in range(5000):
            message = await messages.get(fail=False, timeout=1)
            if message is None:
                break
            event = verified_event(app.state.runtime, message)
            await consume_once(engine, "monitor.run_ready", event, registered)
            await message.ack()
            if event.payload.run_id in run_ids:
                known.add(event.payload.run_id)
        assert known == run_ids
    finally:
        await broker.close()
        async with engine.begin() as conn:
            await execute(conn, f"UPDATE monitors SET desired_enabled=0,state='disabled',"
                          f"next_run_at=NULL WHERE id IN ({predicate})", **params)
    async with engine.connect() as conn:
        completed = await first(
            conn, "SELECT COUNT(*) AS samples,COUNT(DISTINCT s.run_id) AS runs "
            f"FROM monitor_samples s WHERE s.monitor_id IN ({predicate})", **params,
        )
    assert completed["samples"] == completed["runs"] == count and peak <= 5
    ordered = sorted(timings)
    return {"scope": "单进程并发、30ms模拟学校、实际MySQL/Redis/RabbitMQ，非真实学校容量",
            "plans": count, "schedulers": 2, "workers": workers,
            "schedule_seconds": round(scheduling, 3), "capture_seconds": round(capture_seconds, 3),
            "samples_per_second": round(count / capture_seconds, 2),
            "attempt_p50_seconds": round(median(timings), 3),
            "attempt_p95_seconds": round(ordered[int(len(ordered) * 0.95) - 1], 3),
            "school_requests": requests, "school_peak_concurrency": peak,
            "signed_wakeups_confirmed_and_inboxed": len(known),
            "message_seconds": round(time.perf_counter() - message_start, 3),
            "one_sample_per_run": True,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1" or not 8 <= args.plans <= 500:
        raise SystemExit("仅在显式合成隔离环境验证8至500个计划")
    if not 4 <= args.workers <= 16:
        raise SystemExit("并发验证范围为4至16")
    apps, _ = await fixture_apps()
    try:
        print(json.dumps(await run(apps, args.plans, args.workers), ensure_ascii=False))
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
