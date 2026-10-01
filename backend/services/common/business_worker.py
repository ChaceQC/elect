"""T2 持久扫描/租约接管进程；不依赖消息到达才能执行。"""

import argparse
import asyncio
import signal

from .app import create_app
from .heartbeat import Heartbeat
from .job import pause
from .logging import configure_logging, log
from .sql import execute


async def school_cleanup(app):
    async with app.state.database.begin() as conn:
        result = await execute(
            conn,
            "UPDATE credential_staging SET "
            "state=IF(state='activated','activated','expired'),"
            "encrypted_payload='',wrapped_dek='',updated_at=UTC_TIMESTAMP(6) "
            "WHERE expires_at <= UTC_TIMESTAMP(6) AND LENGTH(encrypted_payload)>0",
        )
    return result.rowcount > 0


async def run(service):
    app = create_app(service, business=service != "school_adapter")
    stop, heartbeat = asyncio.Event(), Heartbeat(service, "business")
    for signum in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(signum, stop.set)
    if service == "identity":
        from services.identity.recovery import recover_tick as tick
    elif service == "room":
        from services.room.worker import room_tick as tick
    else:
        tick = school_cleanup
    async with app.router.lifespan_context(app):
        while not stop.is_set():
            try:
                activity = await checked_tick(app, tick, heartbeat)
                heartbeat.write(healthy=True, activity=activity)
            except Exception:
                heartbeat.write(healthy=False)
                log("business_recovery_retry", service=service, error_code="DEPENDENCY_UNAVAILABLE")
            await pause(stop, 1)


async def checked_tick(app, tick, heartbeat):
    task = asyncio.create_task(tick(app))
    try:
        async with asyncio.timeout(120):
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    async with app.state.database.connect() as conn:
                        await execute(conn, "SELECT 1")
                    heartbeat.write(healthy=True)
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
        asyncio.run(run(args.service))
    except Exception:
        raise SystemExit("业务进程启动失败，请检查 Secret 和数据库状态") from None


if __name__ == "__main__":
    main()
