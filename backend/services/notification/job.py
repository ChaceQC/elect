"""持久邮件 Worker/恢复器；MQ 故障不丢已有 job，SMTP 默认关闭。"""

import argparse
import asyncio
import signal
import time

from services.common.app import create_app
from services.common.background import require_standalone
from services.common.broker import Broker
from services.common.business_worker import checked_tick
from services.common.heartbeat import Heartbeat
from services.common.job import pause
from services.common.logging import configure_logging, log

from .consumer import message_tick
from .recovery import recovery_tick
from .worker import worker_tick


async def run(role):
    require_standalone()
    app = create_app("notification", business=True, background=False)
    stop, heartbeat = asyncio.Event(), Heartbeat("notification", role)
    for signum in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(signum, stop.set)
    broker, queue, reconnect_at = None, None, 0
    async with app.router.lifespan_context(app):
        try:
            while not stop.is_set():
                try:
                    if role == "recovery":
                        activity = await recovery_tick(app.state.database)
                    else:
                        if queue is None and time.monotonic() >= reconnect_at:
                            try:
                                broker = Broker(app.state.runtime)
                                await broker.open()
                                queue = await broker.channel.declare_queue(
                                    "elect.notification.alerts", durable=True
                                )
                            except Exception:
                                if broker:
                                    await broker.close()
                                broker, queue, reconnect_at = None, None, time.monotonic() + 15
                        activity = False
                        if queue:
                            try:
                                activity = await checked_tick(
                                app, lambda app, queue=queue: message_tick(app, queue), heartbeat
                                )
                            except Exception:
                                await broker.close()
                                broker, queue, reconnect_at = None, None, time.monotonic() + 15
                        activity = await checked_tick(app, worker_tick, heartbeat) or activity
                    heartbeat.write(healthy=True, activity=activity)
                except Exception:
                    heartbeat.write(healthy=False)
                    log(
                        "notification_job_retry",
                        service="notification",
                        error_code="DEPENDENCY_UNAVAILABLE",
                    )
                await pause(stop, 15 if role == "recovery" else 1)
        finally:
            if broker:
                await broker.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["worker", "recovery"], required=True)
    args = parser.parse_args()
    configure_logging()
    try:
        asyncio.run(run(args.role))
    except Exception:
        raise SystemExit("邮件进程启动失败，请检查 Secret/迁移/内部服务") from None


if __name__ == "__main__":
    main()
