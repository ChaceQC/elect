"""同步、余额和历史共用两个槽，控制Saga保持独立。"""

import asyncio
from functools import partial

from services.common.business_worker import checked_tick
from services.common.job import pause
from services.common.logging import log_failure
from services.common.read_schedule import ReadSchedule
from services.common.read_slots import run_slots
from services.common.scheduling import IdleBackoff


async def room_loop(app, stop, heartbeat, hub=None):
    app.state.read_schedule = ReadSchedule(("binding_sync", "balance_refresh", "history_sync"))
    app.state.read_wakeup_lock = asyncio.Lock()
    try:
        await run_slots(slot_loop, app, stop, heartbeat, hub)
    finally:
        broker = getattr(app.state, "history_broker", None)
        if broker:
            await broker.close()
            app.state.history_broker = None


async def slot_loop(app, stop, heartbeat, hub):
    from .worker import room_tick

    idle = IdleBackoff((1, 2, 5))
    tick = partial(room_tick, stop=stop, hub=hub, heartbeat=heartbeat)
    while not stop.is_set():
        try:
            # 同步/余额无需续租，但等待学校时仍每10秒读库并刷新本槽存活心跳。
            activity = await checked_tick(app, tick, heartbeat, timeout=120)
            heartbeat.write(healthy=True, activity=activity)
        except Exception as error:
            heartbeat.write(healthy=False)
            log_failure("room_read_retry", error, service="room", role="worker")
            activity = False
        await pause(stop, idle.next(activity))
