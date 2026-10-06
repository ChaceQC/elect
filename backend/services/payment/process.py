"""独立支付 Worker/租约恢复器；默认学校写开关关闭。"""

import argparse
from functools import partial

from services.common.app import create_app
from services.common.background import Role, require_standalone, run_standalone
from services.common.job import pause
from services.common.logging import log
from services.common.process_control import run_managed
from services.common.scheduling import IdleBackoff

from .jobs import recover
from .reconciliation import check_tick
from .worker import worker_tick


async def run(role, *, control=None):
    require_standalone()
    app = create_app("payment", business=True, background=False)
    app.state.process_control = control
    configured = [Role(role, partial(role_loop, role))]
    if role == "worker":
        configured.append(Role("reconciliation", partial(role_loop, "reconciliation")))
    async with app.router.lifespan_context(app):
        await run_standalone(app, configured, control)


async def role_loop(role, app, stop, heartbeat, hub=None):
    idle = IdleBackoff((1,) if role == "reconciliation" else (1, 2, 5))
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
                    else await check_tick(app, heartbeat)
                    if role == "reconciliation"
                    else await worker_tick(app, heartbeat, stop=stop)
                )
                heartbeat.write(healthy=True, activity=activity)
            except Exception:
                heartbeat.write(healthy=False)
                log("payment_retry", service="payment", error_code="DEPENDENCY_UNAVAILABLE")
                activity = False
            delay = 1 if role == "recovery" else idle.next(activity)
            queue = getattr(app.state, "payment_queue", None)
            if role == "worker" and getattr(app.state, "payment_broker", None) and queue:
                if await queue.wait(stop, delay):
                    idle.reset()
            else:
                await pause(stop, delay)
    finally:
        broker = getattr(app.state, "payment_broker", None) if role == "worker" else None
        if broker:
            await broker.close()
            app.state.payment_broker = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["worker", "recovery"], required=True)
    args = parser.parse_args()
    run_managed("payment", lambda control: run(args.role, control=control),
                drain_seconds=180 if args.role == "worker" else 30)


if __name__ == "__main__":
    main()
