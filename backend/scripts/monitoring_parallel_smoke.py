"""三个合成账号验证两个执行槽/排队/控制/API/续租，学校出口仅MockTransport。"""

import asyncio
import os
from contextlib import AsyncExitStack

import httpx

from scripts.monitoring_combined_smoke import healthy, run_state, sample_count, until
from scripts.room_test_setup import select_default
from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t4_monitor_smoke import cleanup, enable, run_request
from scripts.t4_query_smoke import QuerySchool
from scripts.t5_fixtures import close_apps
from services.common.background import start_background
from services.common.database import migration_head
from services.common.ids import new_id
from services.common.logging import configure_logging
from services.common.sql import first
from services.room.worker import sync_tick


class HeldSchool:
    def __init__(self, query):
        self.query = query
        self.release = asyncio.Event()
        self.owners, self.active = set(), 0
        self.maximum = 0

    async def handler(self, request):
        if request.url.path.endswith("selectRoomListByUserId"):
            owner = request.url.params["userId"]
            assert owner not in self.owners  # 同一账号不会重叠请求。
            self.owners.add(owner)
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                await self.release.wait()
            finally:
                self.active -= 1
                self.owners.remove(owner)
        return self.query.handler(request)


async def two_slots(engine, runs):
    async with engine.connect() as conn:
        rows = [(await first(conn, "SELECT state,lease_until FROM monitor_runs WHERE id=:id",
                             id=run.bytes)) for run in runs]
    return [row["state"] for row in rows].count("running") == 2


async def verify(apps, school):
    query = QuerySchool(school)
    adapter, app = apps["school_adapter"].state, apps["monitoring"]
    adapter.school_protocol.transport.transport = httpx.MockTransport(query.handler)
    async with AsyncExitStack() as stack:
        clients = [await stack.enter_async_context(browser(apps["gateway"])) for _ in range(3)]
        for client in clients:
            await login(client, await prepare(client, "synthetic-parallel-" + str(new_id())))
            await client.post("/api/v1/room-bindings/sync",
                              headers={"Idempotency-Key": str(new_id())})
            assert await sync_tick(apps["room"])
            await select_default(client, apps["room"], "001")
            await enable(client)
        runs = [await run_request(client) for client in clients]
        held = HeldSchool(query)
        adapter.school_protocol.transport.transport = httpx.MockTransport(held.handler)
        await start_background(app, "monitoring")
        engine = app.state.database
        await until(lambda: two_slots(engine, runs))
        await until(lambda: school_busy(held))
        assert held.maximum == held.active == 2
        async with engine.connect() as conn:
            before = {run: await first(conn, "SELECT state,lease_until FROM monitor_runs "
                                      "WHERE id=:id", id=run.bytes) for run in runs}
        running = [run for run in runs if before[run]["state"] == "running"]
        waiting = next(run for run in runs if run not in running)
        assert await run_state(engine, waiting, "pending")
        assert await adapter.school_store.call("zcard", "school_adapter:background_slots") == 2
        responses = await asyncio.gather(*(client.get("/api/v1/monitor")
                                           for client in clients for _ in range(12)))
        assert all(response.status_code == 200 for response in responses)

        async def renewed():
            async with engine.connect() as conn:
                for run in running:
                    row = await first(conn, "SELECT lease_until FROM monitor_runs WHERE id=:id",
                                      id=run.bytes)
                    if row["lease_until"] <= before[run]["lease_until"]:
                        return False
            return True

        await until(renewed, seconds=16)
        assert app.state.background.available()
        if os.environ.get("ELECT_EFFICIENCY_MQ_DOWN") != "1":
            assert await healthy(app)
        cancelled, closed = running
        cancelled_client = clients[runs.index(cancelled)]
        closed_client = clients[runs.index(closed)]
        value = (await cancelled_client.get(f"/api/v1/monitor/runs/{cancelled}")).json()["data"]
        assert (await cancelled_client.post(f"/api/v1/monitor/runs/{cancelled}/cancel",
                json={"expected_version": value["version"]})).status_code == 200
        monitor = (await closed_client.get("/api/v1/monitor")).json()["data"]
        assert (await closed_client.patch("/api/v1/monitor",
                json={"enabled": False, "expected_version": monitor["version"]})).status_code == 200
        held.release.set()
        await until(lambda: run_state(engine, cancelled, "cancelled"))
        await until(lambda: run_state(engine, closed, "cancelled"))
        await until(lambda: run_state(engine, waiting, "succeeded"))
        assert await sample_count(engine, cancelled) == await sample_count(engine, closed) == 0
        assert await sample_count(engine, waiting) == 1 and held.maximum == 2
        assert await adapter.school_store.call("zcard", "school_adapter:background_slots") == 0
        print({"synthetic_accounts": 3, "worker_slots": 2, "school_peak": held.maximum,
               "shared_background_slots_observed": 2, "queued_third": True,
               "concurrent_control_reads": 36, "both_leases_renewed": True,
               "cancel_and_disable_blocked_samples": True, "queued_run_one_sample": True,
               "mq_available": os.environ.get("ELECT_EFFICIENCY_MQ_DOWN") != "1"})
        await app.state.background.close()
        assert all(task.done() for task in app.state.background.tasks.values())


async def school_busy(held):
    return held.active == 2


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅允许显式一次性环境")
    configure_logging()
    os.environ["ELECT_PROCESS_MODE"], os.environ["ELECT_BACKGROUND_ENABLED"] = "combined", "true"
    apps, school = await fixture_apps()
    for name, app in apps.items():
        app.state.migration_head = migration_head(name) if app.state.database else None
    try:
        await verify(apps, school)
    finally:
        supervisor = getattr(apps["monitoring"].state, "background", None)
        if supervisor:
            supervisor.shutdown_timeout = 0
            await supervisor.close()
        await cleanup(apps["monitoring"])
        await close_apps(apps)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        raise SystemExit("双槽隔离验收失败；未输出凭据/学校载荷") from None
