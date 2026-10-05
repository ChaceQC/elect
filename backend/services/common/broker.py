"""RabbitMQ 持久投递、confirm 与事件签名。"""

import asyncio
import base64

import aio_pika
from cryptography.hazmat.primitives import serialization
from pamqp.commands import Basic

from .internal_dto import EventEnvelope
from .push_consumer import PushConsumer


def signed_message(runtime, event):
    if event.producer != runtime.service:
        raise ValueError("不能代签其他领域事件")
    body = event.model_dump_json().encode()
    key = serialization.load_pem_private_key(runtime.signing_key.get_secret_value().encode(), None)
    return aio_pika.Message(
        body=body,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=str(event.event_id),
        headers={"key_id": runtime.key_id, "signature": base64.b64encode(key.sign(body)).decode()},
    )


def verified_event(runtime, message):
    if len(message.body) > 64 * 1024:
        raise ValueError("事件过大")
    entry = runtime.trust_bundle[message.headers["key_id"]]
    if runtime.service not in entry.audiences or "event:audit" not in entry.scopes:
        raise ValueError("事件权限不符")
    public = serialization.load_pem_public_key(entry.public_key.encode())
    public.verify(base64.b64decode(message.headers["signature"], validate=True), message.body)
    event = EventEnvelope.model_validate_json(message.body)
    if event.producer != entry.issuer or str(event.event_id) != message.message_id:
        raise ValueError("事件身份不符")
    return event


class BrokerHub:
    """一个领域进程复用连接，发布与不同消费者仍使用独立channel。"""

    def __init__(self, runtime):
        self.runtime, self.connection = runtime, None
        self.lock = asyncio.Lock()

    async def open(self):
        async with self.lock:
            if self.connection is None or self.connection.is_closed:
                self.connection = await aio_pika.connect_robust(
                    self.runtime.amqp_url.get_secret_value(), timeout=3
                )
            return self.connection

    async def close(self):
        if self.connection:
            await self.connection.close()


class Broker:
    def __init__(self, runtime, *, hub=None):
        self.runtime = runtime
        self.connection = None
        self.hub = hub
        self.consumers = []

    async def open(self):
        # Robust连接断线时channel.ready也会等待；必须有整体预算才能继续持久扫描。
        async with asyncio.timeout(5):
            self.connection = await self.hub.open() if self.hub else await aio_pika.connect_robust(
                self.runtime.amqp_url.get_secret_value(),
                timeout=3,
            )
            self.channel = await self.connection.channel(
                publisher_confirms=True, on_return_raises=True
            )
            await self.channel.set_qos(prefetch_count=8)
            self.exchange = await self.channel.declare_exchange(
                "elect.events",
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )

    async def audit_queue(self):
        dead = await self.channel.declare_exchange("elect.dead", durable=True)
        dead_queue = await self.channel.declare_queue("elect.audit.dead", durable=True)
        await dead_queue.bind(dead, routing_key="audit")
        queue = await self.channel.declare_queue(
            "elect.audit",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "elect.dead",
                "x-dead-letter-routing-key": "audit",
            },
        )
        await queue.bind(self.exchange, routing_key="audit.recorded")
        return queue

    async def publish(self, event):
        confirmed = await self.exchange.publish(
            signed_message(self.runtime, event), routing_key=event.type, mandatory=True, timeout=10
        )
        if not isinstance(confirmed, Basic.Ack):
            raise RuntimeError("未收到 publisher confirm")

    async def consume(self, queue, *, prefetch=1):
        await self.channel.set_qos(prefetch_count=prefetch)
        consumer = PushConsumer(self.connection, prefetch=prefetch)
        await consumer.start(queue)
        self.consumers.append(consumer)
        return consumer

    async def close(self):
        for consumer in self.consumers:
            consumer.close()
        self.consumers.clear()
        if self.hub:
            if getattr(self, "channel", None):
                await self.channel.close()
        elif self.connection:
            await self.connection.close()
