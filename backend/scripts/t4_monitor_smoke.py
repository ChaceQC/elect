"""T4持久采集实际数据库验收，学校读取使用合成协议。"""

import asyncio
import os
from pathlib import Path
from uuid import UUID

import httpx

from scripts.fixture_time import next_request_minute
from scripts.room_test_setup import select_default
from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t4_query_smoke import QuerySchool
from services.common.dates import today
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.execution import claim_run, renew
from services.monitoring.recovery import acknowledge_cancel, recovery_tick
from services.monitoring.results import fail, succeed
from services.monitoring.scheduler import scheduler_tick
from services.monitoring.worker import execute_run
from services.room.worker import control_tick, sync_tick


async def run_request(client, key=None):
    response = await client.post(
        "/api/v1/monitor/runs", headers={"Idempotency-Key": key or str(new_id())}
    )
    assert response.status_code == 202
    return UUID(response.json()["data"]["run_id"])


async def enable(client):
    monitor = (await client.get("/api/v1/monitor")).json()["data"]
    response = await client.patch(
        "/api/v1/monitor",
        json={
            "enabled": True,
            "email": "synthetic@example.invalid",
            "expected_version": monitor["version"],
        },
    )
    assert response.status_code == 200


async def reject_old(engine, execution):
    try:
        await succeed(engine, execution, "999.99", new_id())
    except ApiError as error:
        assert error.code == "VERSION_CONFLICT"
    else:
        raise AssertionError("失效执行写入了样本")


async def due(engine, run):
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE monitor_runs SET next_attempt_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=run.bytes,
        )


async def cleanup(app):
    configuration = MonitorConfiguration(app.state.database, app.state.email_crypto)
    async with app.state.database.connect() as conn:
        monitors = (
            (
                await execute(
                    conn, "SELECT owner_user_id,version FROM monitors WHERE desired_enabled=1"
                )
            )
            .mappings()
            .all()
        )
    for monitor in monitors:
        await configuration.patch(
            UUID(bytes=monitor["owner_user_id"]),
            MonitorPatch(enabled=False, expected_version=monitor["version"]),
            new_id(),
        )


async def verify(apps, school):
    query_school = QuerySchool(school)
    apps["school_adapter"].state.school_protocol.transport.transport = httpx.MockTransport(
        query_school.handler
    )
    app = apps["monitoring"]
    engine = app.state.database
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, "synthetic-monitor-" + str(new_id())))
        owner = UUID(user["id"])
        await client.post("/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())})
        assert await sync_tick(apps["room"])
        # 学校顺序先返回002；本场景的余额差断言明确针对001。
        await select_default(client, apps["room"], "001")
        await enable(client)
        key = str(new_id())
        run = await run_request(client, key)
        assert await run_request(client, key) == run
        assert await run_request(client) == run
        await asyncio.gather(scheduler_tick(engine), scheduler_tick(engine))
        a, b = await asyncio.gather(claim_run(engine, run), claim_run(engine, run))
        execution = a or b
        assert bool(a) != bool(b) and await renew(engine, execution)
        assert await execute_run(app, execution)
        await reject_old(engine, execution)
        async with engine.connect() as conn:
            count = await first(
                conn, "SELECT COUNT(*) AS n FROM monitor_samples WHERE run_id=:run", run=run.bytes
            )
            assert count["n"] == 1
        print("多Scheduler合并/手动幂等、多Worker互斥/续租、单run唯一成功样本：通过")
        async with engine.begin() as conn:
            await execute(
                conn,
                "UPDATE monitors m JOIN monitor_runs r ON r.monitor_id=m.id "
                "SET m.schedule_anchor_at=r.scheduled_for,m.next_run_at=r.scheduled_for "
                "WHERE r.id=:run",
                run=run.bytes,
            )
        await scheduler_tick(engine)
        async with engine.connect() as conn:
            same_slot = await first(
                conn,
                "SELECT COUNT(*) AS n FROM monitor_runs r JOIN monitors m ON m.id=r.monitor_id "
                "WHERE m.owner_user_id=:owner",
                owner=owner.bytes,
            )
            assert same_slot["n"] == 1
        print("已完成逻辑槽再次到期不重建运行、不复活成功样本：通过")
        query_school.first_balance = "24.30"
        run2 = await run_request(client)
        assert await execute_run(app, await claim_run(engine, run2))
        bindings = (await client.get("/api/v1/room-bindings")).json()["data"]
        target = bindings["default_binding_id"]
        sample_url = (
            f"/api/v1/room-bindings/{target}/monitor-samples"
            f"?start_date=2026-09-01&end_date={today()}&page_size=1"
        )
        first_page = (await client.get(sample_url)).json()["data"]
        assert first_page["total"] == 2 and first_page["items"][0]["balance_delta"] == "-1.20"
        assert (
            first_page["items"][0]["meter_reading"] is None
            and first_page["items"][0]["quality"] == "balance_only"
        )
        assert (await client.get(f"/api/v1/room-bindings/{target}/balance")).json()["data"][
            "amount"
        ] == "24.30"
        late = await run_request(client)
        assert await execute_run(app, await claim_run(engine, late))
        page2 = (
            await client.get(sample_url + "&page=2&snapshot_token=" + first_page["snapshot_token"])
        ).json()["data"]
        assert page2["total"] == 2 and page2["items"][0]["run_id"] == str(run)
        assert page2["items"][0]["balance_delta"] is None
        bad_range = (
            sample_url.replace("2026-09-01", "2026-09-02")
            + "&snapshot_token="
            + first_page["snapshot_token"]
        )
        assert (await client.get(bad_range)).status_code == 400
        async with engine.begin() as conn:
            await execute(
                conn,
                "UPDATE sample_snapshots SET expires_at=UTC_TIMESTAMP(6) "
                "WHERE owner_user_id=:owner",
                owner=owner.bytes,
            )
        assert (
            await client.get(sample_url + "&snapshot_token=" + first_page["snapshot_token"])
        ).status_code == 410
        print(
            "余额差保留负号/首条null，缓存逐目标更新；固定成员分页拒绝迟到新增/范围不符/过期：通过"
        )
        # 后续是另一组故障周期，推进分钟窗口；不放大R4每分钟6键预算。
        await next_request_minute(engine, owner)
        failing = await run_request(client)
        for attempt in range(1, 4):
            execution = await claim_run(engine, failing)
            assert execution
            await fail(engine, execution, "SCHOOL_TIMEOUT", True, new_id())
            state = (await client.get(f"/api/v1/monitor/runs/{failing}")).json()["data"]
            assert state["state"] == ("retry_wait" if attempt < 3 else "failed")
            assert len(state["attempts"]) == attempt
            if attempt < 3:
                await due(engine, failing)
        assert await claim_run(engine, failing) is None
        monitor = (await client.get("/api/v1/monitor")).json()["data"]
        assert monitor["config"]["enabled"] and monitor["health"] == "degraded"
        print("三次attempt/持久退避耗尽，无零样本、不移动成功基线且保留enabled意图：通过")
        crashed = await run_request(client)
        old = await claim_run(engine, crashed)
        async with engine.begin() as conn:
            await execute(
                conn,
                "UPDATE monitor_runs SET lease_until=UTC_TIMESTAMP(6) WHERE id=:id",
                id=crashed.bytes,
            )
        assert await recovery_tick(engine)
        await reject_old(engine, old)
        await due(engine, crashed)
        taken = await claim_run(engine, crashed)
        assert taken.execution_epoch > old.execution_epoch
        assert await execute_run(app, taken)
        cancelling = await run_request(client)
        cancelled_execution = await claim_run(engine, cancelling)
        run_view = (await client.get(f"/api/v1/monitor/runs/{cancelling}")).json()["data"]
        response = await client.post(
            f"/api/v1/monitor/runs/{cancelling}/cancel",
            json={"expected_version": run_view["version"]},
        )
        assert response.json()["data"]["state"] == "cancel_requested"
        await reject_old(engine, cancelled_execution)
        assert await acknowledge_cancel(engine, cancelled_execution)
        assert (await client.get("/api/v1/monitor")).json()["data"]["config"]["enabled"]
        print("租约恢复提升epoch/拒绝旧Worker，运行取消不关闭后续计划：通过")
        old_run = await run_request(client)
        old_execution = await claim_run(engine, old_run)
        second = next(item["id"] for item in bindings["items"] if item["id"] != target)
        response = await client.put(
            "/api/v1/room-preferences/default",
            json={"binding_id": second, "expected_version": bindings["preference_version"]},
        )
        assert response.status_code == 202
        for _ in range(5):
            await control_tick(apps["room"])
        await reject_old(engine, old_execution)
        await acknowledge_cancel(engine, old_execution)
        new_run = await run_request(client)
        assert await execute_run(app, await claim_run(engine, new_run))
        second_url = sample_url.replace(target, second).replace("page_size=1", "page_size=10")
        sample = (await client.get(second_url)).json()["data"]["items"][0]
        assert sample["balance"] == "98.76" and sample["balance_delta"] is None
        assert sample["previous_captured_at"] is None
        print("请求中切换默认拒绝旧提交，新房间98.76独立基线不混入24.30：通过")
        from scripts.t4_process_faults import duplicate_message, kill_claim

        killed = await run_request(client)
        await kill_claim(engine, killed)
        await duplicate_message(app, killed)
        await cleanup(app)
        history = (await client.get(sample_url)).json()["data"]
        assert history["total"] == 4 and history["has_monitor_history"]
        print("关闭后历史/快照仍可读，合成监控全部关闭，可安全恢复真实进程：通过")


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用显式一次性环境")
    apps, school = await fixture_apps()
    try:
        await verify(apps, school)
    finally:
        await cleanup(apps["monitoring"])
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()
    print("T4监控实际MySQL/合成学校验收通过；未连接真实学校/SMTP/支付")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T4监控验收失败（{type(error).__name__}）") from None
