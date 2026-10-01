"""签名事件 -> 本域 Inbox/job；ACK 之前完成持久创建。"""

from services.common.broker import verified_event
from services.common.ids import new_id
from services.common.logging import log
from services.common.outbox import consume_once

from .repository import create_job
from .worker import get_snapshot


async def consume_alert(app, event):
    if event.type != "monitor.alert_reserved" or event.producer != "monitoring":
        raise ValueError("错误提醒事件")
    snapshot = await get_snapshot(app, event.payload, new_id())

    async def handler(conn, event):
        await create_job(
            conn,
            event,
            snapshot,
            app.state.email_crypto,
            app.state.public_origin.removeprefix("https://"),
        )

    return await consume_once(app.state.database, "monitor.alert_reserved", event, handler)


async def message_tick(app, queue):
    message = await queue.get(fail=False, timeout=1)
    if message is None:
        return False
    try:
        event = verified_event(app.state.runtime, message)
        if event.type != "monitor.alert_reserved":
            raise ValueError("错误提醒事件")
    except Exception:
        await message.reject(requeue=False)
        log("notification_event_rejected", service="notification", error_code="INVALID_EVENT")
        return True
    try:
        await consume_alert(app, event)
    except Exception:
        await message.nack(requeue=True)
        raise
    await message.ack()
    return True
