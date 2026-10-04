"""50个真实领域监控集中到期与页面读取；学校仅合成，使用实际SQL/MQ/Redis。"""

import asyncio
import json
import os
import resource
import time
from uuid import UUID

from scripts.domain_combined_smoke import setup
from scripts.monitoring_combined_smoke import until
from scripts.t4_monitor_smoke import enable
from scripts.t5_fixtures import close_apps
from scripts.t6_smoke import account
from services.common.background import start_background
from services.common.domains import CORE_DOMAINS
from services.common.sql import execute, first
from services.core.dispatch import Dispatcher


async def verify(apps, school):
    clients, owners = [], []
    try:
        for _ in range(50):
            client, user, _ = await account(apps, school)
            clients.append(client)
            owners.append(UUID(user["id"]).bytes)
            await enable(client)
        params = {f"o{index}": owner for index, owner in enumerate(owners)}
        predicate = ",".join(f":{key}" for key in params)
        engine = apps["monitoring"].state.database
        async with engine.begin() as conn:
            await execute(conn, "UPDATE monitors SET "
                          "next_run_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND),"
                          "schedule_anchor_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) "
                          f"WHERE owner_user_id IN ({predicate})", **params)
        started = time.perf_counter()
        for name, app in apps.items():
            await start_background(app, name)
        page_reads, semaphore = 0, asyncio.Semaphore(5)

        async def page(client):
            nonlocal page_reads
            async with semaphore:
                response = await client.get("/api/v1/room-bindings")
                assert response.status_code == 200 and response.json()["data"]["items"]
                page_reads += 1

        async def complete():
            async with engine.connect() as conn:
                row = await first(conn, "SELECT COUNT(*) AS n FROM monitor_samples s "
                                  "JOIN monitors m ON m.id=s.monitor_id "
                                  f"WHERE m.owner_user_id IN ({predicate})", **params)
            assert row["n"] <= 50
            return row["n"] == 50

        await asyncio.gather(until(complete, seconds=180),
                             *(page(client) for _ in range(3) for client in clients))
        async with engine.connect() as conn:
            rows = (await execute(conn, "SELECT r.state,COUNT(*) AS n FROM monitor_runs r "
                                  "JOIN monitors m ON m.id=r.monitor_id "
                                  f"WHERE m.owner_user_id IN ({predicate}) GROUP BY r.state",
                                  **params)).mappings().all()
        assert {row["state"]: row["n"] for row in rows} == {"succeeded": 50}
        return {"scope": "隔离单进程真实领域后台/直接调用，学校合成；不是7容器峰值或真实学校容量",
                "plans": 50, "succeeded_runs": 50, "samples": 50,
                "monitoring_slots": 2, "page_reads": page_reads, "page_concurrency": 5,
                "work_seconds": round(time.perf_counter() - started, 3),
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    finally:
        for client in clients:
            await client.aclose()


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("只允许一次性合成项目")
    os.environ["ELECT_PROCESS_MODE"] = "combined"
    apps, school = await setup()
    dispatcher = Dispatcher({name: apps[name] for name in CORE_DOMAINS})
    for app in apps.values():
        app.state.service_client.local = dispatcher
    try:
        print(json.dumps(await verify(apps, school), ensure_ascii=False))
    finally:
        supervisors = [app.state.background for app in apps.values()
                       if getattr(app.state, "background", None)]
        for supervisor in supervisors:
            supervisor.request_stop()
        await asyncio.gather(*(supervisor.close() for supervisor in supervisors))
        await close_apps(apps)


if __name__ == "__main__":
    asyncio.run(main())
