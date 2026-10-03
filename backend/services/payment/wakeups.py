"""签名唤醒只登记 Inbox；丢失/重复消息不能建立或重复执行订单。"""

import asyncio
import time

from services.common.broker import Broker, verified_event
from services.common.outbox import consume_once
from services.common.sql import first


async def registered(conn, event):
    row = await first(
        conn,
        "SELECT owner_user_id FROM payment_orders WHERE id=:id",
        id=event.payload.order_id.bytes,
    )
    if not row or row["owner_user_id"] != event.payload.owner_user_id.bytes:
        raise ValueError("订单唤醒归属不符")


async def drain(app, *, hub=None):
    state = app.state
    if time.monotonic() < getattr(state, "payment_reconnect_at", 0):
        return
    try:
        async with asyncio.timeout(8):
            await receive(app, hub)
    except Exception:
        if getattr(state, "payment_broker", None):
            await state.payment_broker.close()
        state.payment_broker = None
        state.payment_reconnect_at = time.monotonic() + 15


async def receive(app, hub):
    state = app.state
    if not getattr(state, "payment_broker", None):
        state.payment_broker = Broker(state.runtime, hub=hub)
        await state.payment_broker.open()
        await state.payment_broker.channel.set_qos(prefetch_count=1)
        state.payment_queue = await state.payment_broker.channel.declare_queue(
            "elect.payment.orders", durable=True
        )
    message = await state.payment_queue.get(fail=False, timeout=1)
    if message is None:
        return
    try:
        event = verified_event(state.runtime, message)
        if event.type != "payment.order_requested":
            raise ValueError("唤醒类型不符")
    except Exception:
        await message.reject(requeue=False)
        return
    try:
        await consume_once(state.database, "payment.order_requested", event, registered)
    except Exception:
        await message.nack(requeue=True)
        raise
    await message.ack()
