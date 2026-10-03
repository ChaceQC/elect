"""消费历史唤醒提示；进度在MySQL中，MQ故障不阻断扫描。"""

import time

from services.common.broker import Broker, verified_event
from services.common.outbox import consume_once
from services.common.sql import execute


async def registered(conn, event):
    await execute(conn, "SELECT 1")


async def drain(app, *, hub=None):
    state = app.state
    if time.monotonic() < getattr(state, "history_reconnect_at", 0):
        return
    try:
        if not getattr(state, "history_broker", None):
            state.history_broker = Broker(state.runtime, hub=hub)
            await state.history_broker.open()
            await state.history_broker.channel.set_qos(prefetch_count=1)
            state.history_queue = await state.history_broker.channel.declare_queue(
                "elect.room.history", durable=True
            )
        message = await state.history_queue.get(fail=False, timeout=1)
        if message is None:
            return
        try:
            event = verified_event(state.runtime, message)
            if event.type != "room.history_sync_requested":
                raise ValueError("错误历史唤醒")
        except Exception:
            await message.reject(requeue=False)
            return
        try:
            await consume_once(state.database, "room.history_sync_requested", event, registered)
        except Exception:
            await message.nack(requeue=True)
            raise
        await message.ack()
    except Exception:
        if getattr(state, "history_broker", None):
            await state.history_broker.close()
        state.history_broker = None
        state.history_reconnect_at = time.monotonic() + 15
