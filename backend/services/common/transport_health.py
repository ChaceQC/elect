"""只把明确MQ边界的失败归为传输降级；持久业务异常必须保留失败预算。"""

import asyncio

from .sql import execute


class QueueUnavailable(Exception):
    pass


async def receive(queue):
    try:
        async with asyncio.timeout(3):
            return await queue.get(fail=False, timeout=1)
    except Exception:
        raise QueueUnavailable() from None


def degraded(broker, queue):
    if queue is None or broker is None:
        return "rabbitmq"
    if not broker.connection.connected.is_set():
        return "rabbitmq"
    return None


async def transport_scan(engine, role):
    # 不领取/发布；断MQ时验证本域持久队列/Inbox确实仍可扫描，不能仅SELECT 1。
    query = ("SELECT event_id FROM inbox_events LIMIT 1" if role == "audit" else
             "SELECT event_id FROM outbox_events WHERE published_at IS NULL "
             "ORDER BY available_at,event_id LIMIT 1")
    async with asyncio.timeout(3), engine.connect() as conn:
        await execute(conn, query)
