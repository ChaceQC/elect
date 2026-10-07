"""固定合成六类工作共存；实际七域SQL/Redis/MQ与core分派，不代表生产容量。"""

import asyncio
import json
import os
import resource
from time import perf_counter

import httpx
from sqlalchemy import event

from scripts.domain_combined_smoke import setup
from scripts.monitoring_combined_smoke import until
from scripts.r7_mix_support import counts, prepare, stop_synthetic_work
from scripts.t2_smoke import browser, login
from scripts.t2_smoke import prepare as prepare_login
from scripts.t5_fixtures import close_apps
from services.common.background import start_background
from services.common.domains import CORE_DOMAINS
from services.common.ids import new_id
from services.core.dispatch import Dispatcher


def instrument(apps, started):
    peaks, active, waits, hooks = {}, {}, {}, []
    for name, app in apps.items():
        engine = app.state.database
        if engine is not None:
            assert engine.pool.size() == 2 and engine.pool._max_overflow == 1
            active[name] = peaks[name] = 0
            def checkout(*args, domain=name):
                active[domain] += 1
                peaks[domain] = max(peaks[domain], active[domain])
            def checkin(*args, domain=name):
                active[domain] -= 1
            for signal, callback in (("checkout", checkout), ("checkin", checkin)):
                event.listen(engine.sync_engine, signal, callback)
                hooks.append((engine.sync_engine, signal, callback))
        original = app.state.service_client.call
        async def call(service, path, *args, original=original, **kwargs):
            if path in {"/queries/history", "/queries/collect", "/payments/check"}:
                principal = kwargs.get("principal")
                key = (path, principal.user_id if principal else None)
                waits.setdefault(key, perf_counter() - started)
            return await original(service, path, *args, **kwargs)
        app.state.service_client.call = call
    return peaks, waits, hooks


async def verify(apps, school):
    data = await prepare(apps, school)
    started = perf_counter()
    peaks, waits, hooks = instrument(apps, started)
    page_times, login_times = [], []
    adapter = apps["school_adapter"].state
    handler = adapter.school_protocol.transport.transport.handler
    async def delayed(request):
        await asyncio.sleep(.03)  # 固定合成服务时间；不延长业务池事务。
        return handler(request)
    adapter.school_protocol.transport.transport = httpx.MockTransport(delayed)
    completed = asyncio.Event()

    async def pages():
        async def page(client):
            for path in ("auth/session", "monitor", "room-bindings"):
                before = perf_counter()
                response = await client.get("/api/v1/" + path)
                assert response.status_code == 200
                page_times.append(perf_counter() - before)
        while not completed.is_set():
            # 固定并发2，避免页面生成器自己制造无限排队。
            for offset in range(0, len(data[0]), 2):
                await asyncio.gather(*(page(client) for client in data[0][offset:offset + 2]))
            await asyncio.sleep(.05)

    async def logins():
        for _ in range(10):
            async with browser(apps["gateway"]) as client:
                before = perf_counter()
                await login(client, await prepare_login(client, "synthetic-r7-" + str(new_id())))
                login_times.append(perf_counter() - before)

    async def complete():
        return await counts(apps, data) == [10, 10, 10, 0]

    try:
        for name, app in apps.items():
            await start_background(app, name)
        async def finish():
            await asyncio.gather(until(complete, seconds=90), logins())
            completed.set()
        async with asyncio.TaskGroup() as group:
            group.create_task(pages())
            group.create_task(finish())
        supervisors = [app.state.background for app in apps.values()
                       if getattr(app.state, "background", None)]
        failures = sum(beat.snapshot()["failures"] for supervisor in supervisors
                       for beat in supervisor.heartbeats.values())
        assert failures == 0 and all(value <= 3 for value in peaks.values())
        assert len(waits) >= 30 and page_times
        return {"scope": "10账号+10次并行期登录，实际SQL/Redis/MQ/core分派，学校合成",
                "seconds": round(perf_counter() - started, 3), "logins": len(login_times),
                "page_reads": len(page_times), "errors": 0, "error_rate": 0,
                "page_p95_ms": round(sorted(page_times)[int(len(page_times) * .95)] * 1000, 2),
                "login_max_ms": round(max(login_times) * 1000, 2),
                "queue_first_dispatch_max_seconds": {
                    path: round(max(t for (p, _), t in waits.items() if p == path), 3)
                    for path in sorted({p for p, _ in waits})},
                "pool_peak_checked_out": peaks, "completed": await counts(apps, data),
                "remaining_finite_jobs": 0, "periodic_orders": 10, "background_failures": failures,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    finally:
        completed.set()
        supervisors = [app.state.background for app in apps.values()
                       if getattr(app.state, "background", None)]
        for supervisor in supervisors:
            supervisor.request_stop()
        await asyncio.gather(*(supervisor.close() for supervisor in supervisors))
        await stop_synthetic_work(apps, data[1])
        for client in data[0]:
            await client.aclose()
        for engine, signal, callback in hooks:
            event.remove(engine, signal, callback)


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("只允许一次性合成项目")
    os.environ["ELECT_PROCESS_MODE"] = "combined"
    apps, school = await setup()
    dispatcher = Dispatcher({name: apps[name] for name in CORE_DOMAINS})
    for app in apps.values():
        app.state.service_client.local = dispatcher
    try:
        print("R7 mixed " + json.dumps(await verify(apps, school), ensure_ascii=False))
    finally:
        await close_apps(apps)


if __name__ == "__main__":
    asyncio.run(main())
