"""缓存/队列故障作为 degraded 展示，不阻断已持久化控制。"""

import asyncio
from urllib.parse import urlparse

from redis.asyncio import Redis


async def transport_status(runtime):
    checks = {}
    if runtime.redis_url:
        client = Redis.from_url(
            runtime.redis_url.get_secret_value(), socket_connect_timeout=1, socket_timeout=1
        )
        try:
            checks["redis"] = bool(await client.ping())
        except Exception:
            checks["redis"] = False
        finally:
            await client.aclose()
    if runtime.amqp_url:
        parsed = urlparse(runtime.amqp_url.get_secret_value())
        try:
            async with asyncio.timeout(1):
                _, writer = await asyncio.open_connection(parsed.hostname, parsed.port or 5672)
                writer.close()
                await writer.wait_closed()
            checks["rabbitmq"] = True
        except Exception:
            checks["rabbitmq"] = False
    return checks
