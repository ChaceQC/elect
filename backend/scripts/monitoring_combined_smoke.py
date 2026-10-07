"""Monitoring合并角色的真实MySQL/Redis/MQ验收；学校仅使用合成transport。"""

import asyncio
import os
import time
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from uuid import UUID

import httpx

from scripts.room_test_setup import select_default
from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t4_monitor_smoke import cleanup, due, enable, reject_old, run_request
from scripts.t4_query_smoke import QuerySchool
from services.common.background import require_standalone, start_background
from services.common.broker import Broker
from services.common.database import migration_head
from services.common.events import RunReadyPayload
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.sql import execute, first
from services.monitoring.execution import claim_run
from services.room.worker import sync_tick


async def until(check, *, seconds=30):
    async with asyncio.timeout(seconds):
        while not await check():
            await asyncio.sleep(0.1)


async def run_state(engine, run, state):
    async with engine.connect() as conn:
        row = await first(conn, "SELECT state FROM monitor_runs WHERE id=:id", id=run.bytes)
    return row["state"] == state


async def sample_count(engine, run):
    async with engine.connect() as conn:
        row = await first(
            conn, "SELECT COUNT(*) AS n FROM monitor_samples WHERE run_id=:id", id=run.bytes
        )
    return row["n"]


async def stale_hints(app, client):
    cancelled = await run_request(client)
    value = (await client.get(f"/api/v1/monitor/runs/{cancelled}")).json()["data"]
    response = await client.post(
        f"/api/v1/monitor/runs/{cancelled}/cancel", json={"expected_version": value["version"]},
    )
    assert response.status_code == 200
    async with app.state.database.connect() as conn:
        row = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=cancelled.bytes)
    assert row["state"] == "cancelled"
    event = EventEnvelope(
        event_id=new_id(), type="monitor.run_ready", schema_version=1, producer="monitoring",
        aggregate_id=UUID(bytes=row["monitor_id"]), aggregate_version=row["generation"],
        occurred_at=datetime.now(UTC), request_id=new_id(),
        payload=RunReadyPayload(run_id=cancelled, generation=row["generation"]),
        dedupe_key=str(new_id()),
    )
    broker = Broker(app.state.runtime)
    try:
        await broker.open()
        for _ in range(50):
            await broker.publish(event)
    finally:
        await broker.close()
    print("预置50条签名的已终结/重复唤醒，验证积压不能阻断新持久任务")


class ControlledCollection:
    def __init__(self, client):
        self.call = client.call
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.calls = 0
        client.call = self.invoke

    def block(self):
        self.entered.clear()
        self.release.clear()

    async def invoke(self, receiver, path, *args, **kwargs):
        if receiver == "school_adapter" and path == "/queries/collect":
            self.calls += 1
            self.entered.set()
            await self.release.wait()
        return await self.call(receiver, path, *args, **kwargs)


async def healthy(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://monitoring"
    ) as client:
        response = await client.get("/health/ready")
        return response.status_code == 200 and response.json()["status"] == "ready"


async def verify_pool_progress(app, client, run):
    engine = app.state.database
    async with engine.connect() as conn:
        before = await first(
            conn, "SELECT lease_until FROM monitor_runs WHERE id=:id", id=run.bytes,
        )
    started = time.perf_counter()
    responses = await asyncio.gather(*(client.get("/api/v1/monitor") for _ in range(50)))
    assert all(response.status_code == 200 for response in responses)
    api_seconds = time.perf_counter() - started
    assert await healthy(app)

    async def renewed():
        async with engine.connect() as conn:
            after = await first(conn, "SELECT lease_until FROM monitor_runs WHERE id=:id",
                                id=run.bytes)
        return after["lease_until"] > before["lease_until"]

    await until(renewed, seconds=16)
    assert app.state.background.available() and await healthy(app)
    print({"pool_capacity": engine.pool.size() + engine.pool._max_overflow,
           "concurrent_control_reads": 50, "api_batch_seconds": round(api_seconds, 4),
           "lease_renewed_during_school_wait": True, "roles_healthy": True})


async def verify_cycle(app, client, collection, owner):
    engine = app.state.database
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE monitors SET next_run_at=UTC_TIMESTAMP(6) WHERE owner_user_id=:id",
            id=owner.bytes,
        )
    await start_background(app, "monitoring")
    supervisor = app.state.background
    assert set(supervisor.tasks) == {"relay", "scheduler", "worker", "recovery", "alerts"}
    await asyncio.wait_for(collection.entered.wait(), 30)
    await until(lambda: healthy(app))
    # 学校等待不占持久事务；同一池内的控制/健康请求仍可继续。
    assert (await client.get("/api/v1/monitor")).status_code == 200
    # 双槽与其他角色会短时借连接；实际取得完整池容量确认学校等待不持有连接。
    async with AsyncExitStack() as connections:
        for _ in range(engine.pool.size() + engine.pool._max_overflow):
            await connections.enter_async_context(engine.connect())
    async with engine.connect() as conn:
        row = await first(
            conn,
            "SELECT active_run_id FROM monitors WHERE owner_user_id=:id",
            id=owner.bytes,
        )
    scheduled = UUID(bytes=row["active_run_id"])
    await verify_pool_progress(app, client, scheduled)
    collection.release.set()
    await until(lambda: run_state(engine, scheduled, "succeeded"))
    assert await sample_count(engine, scheduled) == 1
    print("API与五个后台角色并存、共享本域池/客户端、真实AMQP发布和调度采集：通过")


async def verify_cancel(app, client, collection):
    collection.block()
    cancelled = await run_request(client)
    await asyncio.wait_for(collection.entered.wait(), 30)
    value = (await client.get(f"/api/v1/monitor/runs/{cancelled}")).json()["data"]
    response = await client.post(
        f"/api/v1/monitor/runs/{cancelled}/cancel", json={"expected_version": value["version"]}
    )
    assert response.json()["data"]["state"] == "cancel_requested"
    collection.release.set()
    await until(lambda: run_state(app.state.database, cancelled, "cancelled"))
    assert await sample_count(app.state.database, cancelled) == 0
    print("合并Worker请求中取消、迟到结果不写样本：通过")


async def verify_recovery(app, client):
    engine, supervisor = app.state.database, app.state.background
    supervisor.tasks["worker"].cancel()
    await asyncio.gather(supervisor.tasks["worker"], return_exceptions=True)
    assert not await healthy(app) and not supervisor.available()
    # R3角色失败会协调停止整个生命周期；旧恢复器不能继续领取。
    await supervisor.close()
    assert supervisor.stop.is_set() and all(task.done() for task in supervisor.tasks.values())
    crashed = await run_request(client)
    old = await claim_run(engine, crashed)
    assert old
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE monitor_runs SET lease_until=UTC_TIMESTAMP(6) WHERE id=:id",
            id=crashed.bytes,
        )
    await reject_old(engine, old)
    await start_background(app, "monitoring")
    await until(lambda: run_state(engine, crashed, "retry_wait"))
    await due(engine, crashed)
    await until(lambda: run_state(engine, crashed, "succeeded"))
    assert await sample_count(engine, crashed) == 1
    await until(lambda: healthy(app))
    print("单角色退出协调停止、重建生命周期后接管、旧epoch失效/同run单样本：通过")


async def verify_shutdown(app, client, collection):
    supervisor = app.state.background
    collection.block()
    draining = await run_request(client)
    await asyncio.wait_for(collection.entered.wait(), 30)
    supervisor.request_stop()
    closing = asyncio.create_task(supervisor.close())
    await asyncio.sleep(0.1)
    assert not closing.done() and not supervisor.available()
    claims = collection.calls
    collection.release.set()
    await closing
    assert collection.calls == claims
    assert await run_state(app.state.database, draining, "succeeded")
    assert all(task.done() for task in supervisor.tasks.values())
    assert supervisor.broker.connection is None or supervisor.broker.connection.is_closed
    print("停止领取后等待在途提交，全部角色/channel/共享连接退出：通过")
    os.environ["ELECT_BACKGROUND_ENABLED"] = "false"
    await start_background(app, "monitoring")
    assert app.state.background is None
    try:
        require_standalone()
    except RuntimeError:
        pass
    else:
        raise AssertionError("恢复隔离允许启动独立后台")
    print("恢复禁用覆盖合并模式，同时拒绝独立后台入口：通过")


async def verify(apps, school):
    app = apps["monitoring"]
    app.state.migration_head = migration_head("monitoring")
    query = QuerySchool(school)
    apps["school_adapter"].state.school_protocol.transport.transport = httpx.MockTransport(
        query.handler
    )
    collection = ControlledCollection(app.state.service_client)
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, "synthetic-combined-" + str(new_id())))
        await client.post("/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())})
        assert await sync_tick(apps["room"])
        await select_default(client, apps["room"], "001")
        await enable(client)
        await stale_hints(app, client)
        await verify_cycle(app, client, collection, UUID(user["id"]))
        await verify_cancel(app, client, collection)
        await verify_recovery(app, client)
        await verify_shutdown(app, client, collection)


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于显式一次性环境")
    os.environ["ELECT_PROCESS_MODE"] = "combined"
    os.environ["ELECT_BACKGROUND_ENABLED"] = "true"
    apps, school = await fixture_apps()
    try:
        await verify(apps, school)
    finally:
        supervisor = getattr(apps["monitoring"].state, "background", None)
        if supervisor:
            # 失败路径先停止/取消，不能在清理账号时继续领取合成任务。
            supervisor.shutdown_timeout = 0
            await supervisor.close()
        await cleanup(apps["monitoring"])
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{frame.name}:{frame.lineno}")
        raise SystemExit(f"合并角色验收失败（{type(error).__name__}）") from None
