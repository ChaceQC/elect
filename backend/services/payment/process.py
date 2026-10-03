"""独立支付 Worker/租约恢复器；默认学校写开关关闭。"""

import argparse
import asyncio
import signal

from services.common.app import create_app
from services.common.background import require_standalone
from services.common.heartbeat import Heartbeat
from services.common.job import pause
from services.common.logging import log

from .jobs import recover
from .worker import worker_tick


async def run(role):
    require_standalone()
    app = create_app("payment", business=True, background=False)
    stop, heartbeat = asyncio.Event(), Heartbeat("payment", role)
    for signum in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(signum, stop.set)
    async with app.router.lifespan_context(app):
        await role_loop(role, app, stop, heartbeat)


async def role_loop(role, app, stop, heartbeat, hub=None):
    try:
        while not stop.is_set():
            try:
                if role == "worker":
                    from .wakeups import drain

                    await drain(app, hub=hub)
                    if stop.is_set():
                        break
                activity = (
                    await recover(app.state.database)
                    if role == "recovery"
                    else await worker_tick(app, heartbeat, stop=stop)
                )
                heartbeat.write(healthy=True, activity=activity)
            except Exception:
                heartbeat.write(healthy=False)
                log("payment_retry", service="payment", error_code="DEPENDENCY_UNAVAILABLE")
            await pause(stop, 1)
    finally:
        broker = getattr(app.state, "payment_broker", None)
        if broker:
            await broker.close()
            app.state.payment_broker = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["worker", "recovery"], required=True)
    args = parser.parse_args()
    asyncio.run(run(args.role))


if __name__ == "__main__":
    main()
