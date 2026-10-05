"""显式隔离环境的真实Redis/MySQL中断；学校请求始终是合成transport。"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

import httpx

from scripts.room_test_setup import ready_default
from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t4_monitor_smoke import enable
from scripts.t4_query_smoke import QuerySchool
from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.execution import claim_run
from services.monitoring.recovery import recovery_tick
from services.monitoring.worker import execute_run, worker_tick
from services.room.worker import sync_tick


async def prepared(apps, path):
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, "synthetic-dependency-" + str(new_id())))
        await client.post("/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())})
        assert await sync_tick(apps["room"])
        await ready_default(client, apps["room"])
        await enable(client)
        response = await client.post(
            "/api/v1/monitor/runs", headers={"Idempotency-Key": str(new_id())}
        )
        assert response.status_code == 202
        path.write_text(json.dumps({"run": response.json()["data"]["run_id"], "owner": user["id"]}))
    print("依赖故障合成运行已持久受理")


async def redis_down(apps, run):
    try:
        await apps["school_adapter"].state.redis.ping()
    except Exception:
        pass
    else:
        raise AssertionError("Redis尚可达")
    execution = await claim_run(apps["monitoring"].state.database, run)
    assert execution
    assert not await execute_run(apps["monitoring"], execution)
    async with apps["monitoring"].state.database.connect() as conn:
        row = await first(
            conn,
            "SELECT state,error_code,next_attempt_at FROM monitor_runs WHERE id=:id",
            id=run.bytes,
        )
        assert row["state"] == "retry_wait" and row["error_code"] == "DEPENDENCY_UNAVAILABLE"
        assert row["next_attempt_at"]
    print("真实Redis中断：失败持久retry_wait、未写零样本：通过")


async def map_token(apps, school, owner):
    repository = apps["school_adapter"].state.school_credentials
    credential = await repository.current(owner)
    student = repository.payload(credential)["student_id"]
    assert student.startswith("synthetic-dependency-")
    cached = await apps["school_adapter"].state.school_store.get_secret(
        f"school_adapter:token:{UUID(bytes=credential['id'])}:{credential['version']}"
    )
    if cached:
        school.tokens[cached["token"]] = student


async def hold(apps, school, state, path):
    await map_token(apps, school, UUID(state["owner"]))
    query = QuerySchool(school)

    async def handler(request):
        if request.url.path.endswith("selectRoomListByUserId"):
            path.with_suffix(".ready").touch()
            await asyncio.Event().wait()
        return query.handler(request)

    apps["school_adapter"].state.school_protocol.transport.transport = httpx.MockTransport(handler)
    engine = apps["monitoring"].state.database
    run = UUID(state["run"])
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE monitor_runs SET next_attempt_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=run.bytes,
        )
    execution = await claim_run(engine, run)
    assert execution
    try:
        await execute_run(apps["monitoring"], execution)
    except Exception:
        # HTTP取消和数据库断连发生在同一attempt；重启后再核对没有样本。
        pass
    else:
        raise AssertionError("未发生MySQL续租/提交失败")
    print("真实MySQL中断：续租失败结束合成学校请求，未声称成功：通过")


async def recovered(apps, school, state):
    owner, run = UUID(state["owner"]), UUID(state["run"])
    await map_token(apps, school, owner)
    # 测试把MySQL45秒租约和30秒重试提前推进；原合成读取进程已退出，
    # 同步推进其Redis账号锁租约，避免只推进一种时钟导致人为提前耗尽attempt。
    from services.school_adapter.infrastructure.crypto import lookup_aliases

    adapter = apps["school_adapter"].state
    credential = await adapter.school_credentials.current(owner)
    student = adapter.school_credentials.payload(credential)["student_id"]
    assert student.startswith("synthetic-dependency-")
    lookup = adapter.school_sessions.lookup
    alias = lookup_aliases(lookup, "hbue", student)[lookup.current]
    await adapter.school_store.call("expire", f"school_adapter:account_lock:{alias}", 0)
    engine = apps["monitoring"].state.database
    async with engine.begin() as conn:
        count = await first(
            conn, "SELECT COUNT(*) AS n FROM monitor_samples WHERE run_id=:id", id=run.bytes
        )
        assert count["n"] == 0
        await execute(
            conn, "UPDATE monitor_runs SET lease_until=UTC_TIMESTAMP(6) WHERE id=:id", id=run.bytes
        )
    await recovery_tick(engine)
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE monitor_runs SET next_attempt_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=run.bytes,
        )
    assert await worker_tick(apps["monitoring"], run)
    async with engine.connect() as conn:
        row = await first(
            conn, "SELECT state,attempt_count FROM monitor_runs WHERE id=:id", id=run.bytes
        )
        assert row["state"] == "succeeded" and row["attempt_count"] == 3
        count = await first(
            conn, "SELECT COUNT(*) AS n FROM monitor_samples WHERE run_id=:id", id=run.bytes
        )
        assert count["n"] == 1
    config = MonitorConfiguration(engine, apps["monitoring"].state.email_crypto)
    monitor = await config.get(owner)
    await config.patch(
        owner, MonitorPatch(enabled=False, expected_version=monitor.version), new_id()
    )
    print("Redis/MySQL重建后同run第三次成功、仅一条样本、测试监控关闭：通过")


async def main(mode, path):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于一次性测试")
    apps, school = await fixture_apps()
    query = QuerySchool(school)
    apps["school_adapter"].state.school_protocol.transport.transport = httpx.MockTransport(
        query.handler
    )
    try:
        if mode == "prepare":
            await prepared(apps, path)
        else:
            state = json.loads(path.read_text())
            if mode == "redis-down":
                await redis_down(apps, UUID(state["run"]))
            elif mode == "hold":
                await hold(apps, school, state, path)
            elif mode == "close":
                owner = UUID(state["owner"])
                await map_token(apps, school, owner)
                config = MonitorConfiguration(
                    apps["monitoring"].state.database, apps["monitoring"].state.email_crypto
                )
                current = await config.get(owner)
                await config.patch(
                    owner, MonitorPatch(enabled=False, expected_version=current.version), new_id()
                )
            else:
                await recovered(apps, school, state)
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["prepare", "redis-down", "hold", "recover", "close"], required=True
    )
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.mode, args.record))
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"依赖故障验收失败（{type(error).__name__}）") from None
