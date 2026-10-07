"""持久邮件 Worker/恢复器；MQ 故障不丢已有 job，SMTP 默认关闭。"""

import argparse
import asyncio
import time
from functools import partial
from types import SimpleNamespace

from services.common.background import Role, require_standalone, run_standalone
from services.common.broker import Broker
from services.common.business_worker import checked_tick
from services.common.context import domain_context
from services.common.job import pause
from services.common.logging import configure_logging, log
from services.common.process_control import run_managed
from services.common.scheduling import IdleBackoff, retry_delay
from services.common.transport_health import QueueUnavailable, degraded

from .consumer import message_tick
from .recovery import recovery_tick
from .worker import worker_tick


async def run(role, *, control=None):
    require_standalone()
    app = SimpleNamespace(state=SimpleNamespace(process_control=control))
    async with domain_context(app, "notification"):
        await run_standalone(app, [Role(role, partial(role_loop, role),
                                       max_age=45 if role == "recovery" else 20)], control)


async def role_loop(role, app, stop, heartbeat, hub=None):
    broker, queue, reconnect_at = None, None, 0
    idle = IdleBackoff((1, 2, 5))
    try:
        while not stop.is_set():
            try:
                if role == "recovery":
                    activity = await recovery_tick(app.state.database)
                else:
                    if queue is None and time.monotonic() >= reconnect_at:
                        try:
                            broker = Broker(app.state.runtime, hub=hub)
                            async with asyncio.timeout(8):
                                await broker.open()
                                queue = await broker.channel.declare_queue(
                                    "elect.notification.alerts", durable=True
                                )
                                queue = await broker.consume(queue)
                        except Exception:
                            if broker:
                                await broker.close()
                            broker, queue = None, None
                            reconnect_at = time.monotonic() + retry_delay(4, maximum=15)
                    activity = False
                    if queue:
                        try:
                            activity = await checked_tick(
                                app, lambda app, queue=queue: message_tick(app, queue), heartbeat
                            )
                        except QueueUnavailable:
                            await broker.close()
                            broker, queue = None, None
                            reconnect_at = time.monotonic() + retry_delay(4, maximum=15)
                    if not stop.is_set():
                        activity = await checked_tick(
                            app, partial(worker_tick, heartbeat=heartbeat), heartbeat,
                        ) or activity
                heartbeat.write(healthy=True, activity=activity,
                                degraded=degraded(broker, queue) if role == "worker" else None)
            except Exception:
                heartbeat.write(healthy=False)
                log(
                    "notification_job_retry", service="notification",
                    error_code="DEPENDENCY_UNAVAILABLE",
                )
                activity = False
            delay = 15 if role == "recovery" else idle.next(activity)
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
    parser.add_argument("--role", choices=["worker", "recovery"], required=True)
    args = parser.parse_args()
    configure_logging()
    try:
        run_managed("notification", lambda control: run(args.role, control=control))
    except Exception:
        raise SystemExit("邮件进程启动失败，请检查 Secret/迁移/内部服务") from None


if __name__ == "__main__":
    main()
