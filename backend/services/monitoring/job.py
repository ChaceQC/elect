"""独立 Scheduler/Worker/恢复器入口；队列不可用时仍扫描持久任务。"""

import argparse
import asyncio
import signal
import time

from services.common.app import create_app
from services.common.broker import Broker, verified_event
from services.common.heartbeat import Heartbeat
from services.common.job import pause
from services.common.logging import configure_logging, log
from services.common.outbox import consume_once

from .execution import claim_run
from .recovery import recovery_tick
from .scheduler import scheduler_tick
from .worker import execute_run


async def registered(conn, event):
    # 唤醒处理已先尝试持久领取；没有有效任务也可ACK，恢复使用新event_id。
    from services.common.sql import execute

    await execute(conn, "SELECT 1")


async def message_tick(app, queue, heartbeat):
    message = await queue.get(fail=False, timeout=1)
    if message is None:
        return False
    try:
        event = verified_event(app.state.runtime, message)
        if event.type != "monitor.run_ready":
            raise ValueError("错误唤醒类型")
    except Exception:
        await message.reject(requeue=False)
        log("monitor_event_rejected", service="monitoring", error_code="INVALID_EVENT")
        return True
    try:
        execution = await claim_run(app.state.database, event.payload.run_id)
        await consume_once(app.state.database, "monitor.run_ready", event, registered)
    except Exception:
        await message.nack(requeue=True)
        raise
    # 领取状态已经提交；此后崩溃由MySQL租约恢复。
    await message.ack()
    if execution:
        await execute_run(app, execution, heartbeat)
    return True


async def run(role):
    app = create_app("monitoring", business=True)
    stop, heartbeat = asyncio.Event(), Heartbeat("monitoring", role)
    for signum in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(signum, stop.set)
    broker, queue, reconnect_at = None, None, 0
    async with app.router.lifespan_context(app):
        try:
            while not stop.is_set():
                try:
                    if role == "worker":
                        if queue is None and time.monotonic() >= reconnect_at:
                            try:
                                broker = Broker(app.state.runtime)
                                await broker.open()
                                await broker.channel.set_qos(prefetch_count=1)
                                queue = await broker.channel.declare_queue(
                                    "elect.monitoring.runs", durable=True
                                )
                            except Exception:
                                if broker:
                                    await broker.close()
                                broker, queue = None, None
                                reconnect_at = time.monotonic() + 15
                        try:
                            activity = await message_tick(app, queue, heartbeat) if queue else False
                        except Exception:
                            await broker.close()
                            broker, queue = None, None
                            reconnect_at = time.monotonic() + 15
                            activity = False
                        if not activity:
                            from .worker import worker_tick

                            activity = await worker_tick(app, heartbeat=heartbeat)
                    else:
                        activity = await (scheduler_tick if role == "scheduler" else recovery_tick)(
                            app.state.database
                        )
                    heartbeat.write(healthy=True, activity=activity)
                except Exception:
                    heartbeat.write(healthy=False)
                    log(
                        "monitor_job_retry",
                        service="monitoring",
                        error_code="DEPENDENCY_UNAVAILABLE",
                    )
                await pause(stop, {"scheduler": 5, "recovery": 15, "worker": 1}[role])
        finally:
            if broker:
                await broker.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["scheduler", "worker", "recovery"], required=True)
    args = parser.parse_args()
    configure_logging()
    try:
        asyncio.run(run(args.role))
    except Exception:
        raise SystemExit("监控进程启动失败，请检查Secret/迁移/内部TLS") from None


if __name__ == "__main__":
    main()
