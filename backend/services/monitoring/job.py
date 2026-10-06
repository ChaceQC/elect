"""独立 Scheduler/Worker/恢复器入口；队列不可用时仍扫描持久任务。"""

import argparse
import asyncio
import time
from functools import partial

from services.common.app import create_app
from services.common.background import Role, require_standalone, run_standalone
from services.common.broker import Broker, BrokerHub, verified_event
from services.common.job import pause, transport_loop
from services.common.logging import configure_logging, log
from services.common.outbox import consume_once
from services.common.process_control import run_managed
from services.common.scheduling import IdleBackoff, retry_delay
from services.common.transport_health import QueueUnavailable, degraded, receive

from .execution import claim_run
from .recovery import recovery_tick
from .scheduler import scheduler_tick
from .worker import execute_run


async def registered(conn, event):
    # run提示先尝试持久领取；绑定确认的控制已由Saga持久协调，事件只记Inbox。
    from services.common.sql import execute

    await execute(conn, "SELECT 1")


async def message_tick(app, queue, heartbeat, stop=None):
    message = await receive(queue)
    if message is None:
        return False
    if stop and stop.is_set():
        await message.nack(requeue=True)
        return False
    try:
        event = verified_event(app.state.runtime, message)
        if event.type not in {"monitor.run_ready", "room.binding_confirmed"}:
            raise ValueError("错误唤醒类型")
    except Exception:
        await message.reject(requeue=False)
        log("monitor_event_rejected", service="monitoring", error_code="INVALID_EVENT")
        return True
    try:
        execution = (
            await claim_run(app.state.database, event.payload.run_id)
            if event.type == "monitor.run_ready" else None
        )
        await consume_once(app.state.database, event.type, event, registered)
    except Exception:
        await message.nack(requeue=True)
        raise
    # 领取状态已经提交；此后崩溃由MySQL租约恢复。
    await message.ack()
    if execution:
        if heartbeat:
            heartbeat.tick()
        await execute_run(app, execution, heartbeat)
    return True


async def run(role, *, control=None):
    require_standalone()
    app = create_app("monitoring", business=True, background=False)
    app.state.process_control = control
    async with app.router.lifespan_context(app):
        await run_standalone(app, [Role(role, partial(role_loop, role),
                                       max_age=45 if role == "recovery" else 20)], control)


def roles():
    return [Role("relay", transport_loop, max_age=45), *(
        Role(role, partial(role_loop, role), max_age=45 if role == "recovery" else 20)
        for role in ("scheduler", "worker", "recovery", "alerts")
    )]


async def connect_queue(app, role, hub):
    broker = Broker(app.state.runtime, hub=hub)
    try:
        async with asyncio.timeout(8):
            await broker.open()
            queue = await broker.channel.declare_queue(
                "elect.monitoring.runs" if role == "worker" else "elect.monitoring.deliveries",
                durable=True,
            )
            queue = await broker.consume(queue)
        return broker, queue
    except Exception:
        await broker.close()
        raise


async def consumer_tick(role, app, queue, heartbeat, stop):
    if stop.is_set():
        return False
    if role == "alerts":
        from .alert_recovery import report_tick, wake_tick

        activity = await report_tick(app, queue) if queue else False
        return await wake_tick(app.state.database) or activity
    activity = await message_tick(app, queue, heartbeat, stop) if queue else False
    # 已终结/重复的MQ提示也算已处理，不能因此跳过本轮的持久领取。
    if not stop.is_set():
        from .worker import worker_tick

        activity = await worker_tick(app, heartbeat=heartbeat) or activity
    return activity


async def role_loop(role, app, stop, heartbeat, hub=None):
    if role != "worker":
        return await scan_loop(role, app, stop, heartbeat, hub)
    shared = hub or BrokerHub(app.state.runtime)
    try:
        # 两个槽共用本域engine/client/AMQP连接，各有prefetch=1的独立channel。
        async with asyncio.TaskGroup() as tasks:
            for slot in range(2):
                tasks.create_task(
                    slot_loop(app, stop, heartbeat.child(str(slot)), shared),
                    name=f"monitor-slot:{slot}",
                )
    finally:
        if hub is None:
            await shared.close()


async def slot_loop(app, stop, heartbeat, hub):
    try:
        await scan_loop("worker", app, stop, heartbeat, hub)
    except asyncio.CancelledError:
        if not stop.is_set():
            raise RuntimeError("监控执行槽意外取消") from None
        raise
    if not stop.is_set():
        raise RuntimeError("监控执行槽意外返回")


async def scan_loop(role, app, stop, heartbeat, hub=None):
    broker, queue, reconnect_at = None, None, 0
    next_snapshot_cleanup = 0
    idle = IdleBackoff((1, 2, 5) if role == "worker" else (1, 2, 5, 10))
    try:
        while not stop.is_set():
            try:
                if role in {"worker", "alerts"}:
                    if queue is None and time.monotonic() >= reconnect_at:
                        try:
                            broker, queue = await connect_queue(app, role, hub)
                        except Exception:
                            broker, queue = None, None
                            reconnect_at = time.monotonic() + retry_delay(4, maximum=15)
                    try:
                        activity = await consumer_tick(role, app, queue, heartbeat, stop)
                    except QueueUnavailable:
                        if broker:
                            await broker.close()
                        broker, queue = None, None
                        reconnect_at = time.monotonic() + retry_delay(4, maximum=15)
                        activity = await consumer_tick(role, app, None, heartbeat, stop)
                else:
                    activity = await (scheduler_tick if role == "scheduler" else recovery_tick)(
                        app.state.database
                    )
                    if role == "recovery" and time.monotonic() >= next_snapshot_cleanup:
                        from .snapshot_cleanup import cleanup_snapshots

                        await cleanup_snapshots(app.state.database)
                        next_snapshot_cleanup = time.monotonic() + 60
                heartbeat.write(healthy=True, activity=activity,
                                degraded=degraded(broker, queue)
                                if role in {"worker", "alerts"} else None)
            except Exception:
                heartbeat.write(healthy=False)
                log("monitor_job_retry", service="monitoring", error_code="DEPENDENCY_UNAVAILABLE")
                activity = False
            delay = {"scheduler": 5, "recovery": 15}.get(role)
            if delay is None:
                delay = idle.next(activity)
            if queue:
                if await queue.wait(stop, delay):
                    idle.reset()
            else:
                await pause(stop, delay)
    finally:
        if broker:
            await broker.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--role", choices=["scheduler", "worker", "recovery", "alerts"], required=True
    )
    args = parser.parse_args()
    configure_logging()
    try:
        run_managed("monitoring", lambda control: run(args.role, control=control),
                    drain_seconds=100 if args.role == "worker" else 30)
    except Exception:
        raise SystemExit("监控进程启动失败，请检查Secret/迁移/内部TLS") from None


if __name__ == "__main__":
    main()
