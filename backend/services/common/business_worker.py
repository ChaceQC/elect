"""T2 持久扫描/租约接管进程；不依赖消息到达才能执行。"""

import argparse
import asyncio
import time
from functools import partial

from .background import Role, require_standalone, run_standalone
from .background_roles import BUSINESS_ROLES
from .job import pause
from .logging import configure_logging, log
from .process_control import run_managed
from .sql import execute


async def school_cleanup(app):
    from services.school_adapter.retention import cleanup

    return bool((await cleanup(app.state.database))["staging"])


async def run(service, *, control=None):
    from .app import create_app

    require_standalone()
    app = create_app(service, business=service != "school_adapter", background=False)
    app.state.process_control = control
    configured = [Role(BUSINESS_ROLES[service], partial(business_loop, service))]
    if service == "room":
        configured.append(Role("control", partial(business_loop, "room_control")))
    async with app.router.lifespan_context(app):
        await run_standalone(app, configured, control)


async def business_loop(service, app, stop, heartbeat, hub=None):
    if service == "identity":
        from services.identity.recovery import recover_tick as tick

        tick = partial(tick, stop=stop)
    elif service == "room_control":
        from services.room.worker import control_tick as tick
    elif service == "room":
        from services.room.worker import room_tick as tick

        tick = partial(tick, stop=stop, hub=hub, heartbeat=heartbeat)
    else:
        tick = school_cleanup
    next_cleanup = 0
    next_session_cleanup = 0
    try:
        while not stop.is_set():
            try:
                if service == "school_adapter" and time.monotonic() < next_cleanup:
                    async with app.state.database.connect() as conn:
                        await execute(conn, "SELECT 1")
                    heartbeat.tick()
                    activity = False
                else:
                    activity = await checked_tick(
                        app, tick, heartbeat, timeout=None if service == "room" else 120,
                    )
                    if (service == "identity" and not stop.is_set()
                            and time.monotonic() >= next_session_cleanup):
                        from services.identity.retention import cleanup

                        await cleanup(app.state.database)
                        next_session_cleanup = time.monotonic() + 60
                    if service == "school_adapter":
                        next_cleanup = time.monotonic() + (0 if activity else 60)
                    heartbeat.write(healthy=True, activity=activity, next_scan_in=(
                        60 if service == "school_adapter" and not activity else None
                    ))
            except Exception:
                heartbeat.write(healthy=False)
                log("business_recovery_retry", service=service, error_code="DEPENDENCY_UNAVAILABLE")
                activity = False
            # Adapter每批至多200行，积压继续小批；真实读库每10秒保留健康。
            delay = (0 if activity else 10) if service == "school_adapter" else 1
            await pause(stop, delay)
    finally:
        broker = getattr(app.state, "history_broker", None) if service == "room" else None
        if broker:
            await broker.close()
            app.state.history_broker = None


async def checked_tick(app, tick, heartbeat, *, timeout=120):
    with heartbeat.work(timeout if timeout is not None else 250):
        return await _checked_tick(app, tick, heartbeat, timeout=timeout)


async def _checked_tick(app, tick, heartbeat, *, timeout):
    task = asyncio.create_task(tick(app))
    try:
        async with asyncio.timeout(timeout):
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    async with app.state.database.connect() as conn:
                        await execute(conn, "SELECT 1")
                    heartbeat.tick()
            return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=["identity", "room", "school_adapter"], required=True)
    args = parser.parse_args()
    configure_logging()
    try:
        run_managed(args.service, lambda control: run(args.service, control=control))
    except Exception:
        raise SystemExit("业务进程启动失败，请检查 Secret 和数据库状态") from None


if __name__ == "__main__":
    main()
