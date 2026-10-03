import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services.common.broker import Broker
from services.common.push_consumer import PushConsumer


def test_consumer_uses_bounded_push_and_never_acks_before_domain_commit():
    async def verify():
        callbacks = set()
        connection = SimpleNamespace(reconnect_callbacks=callbacks)
        queue = SimpleNamespace(consume=AsyncMock(), get=Mock(side_effect=AssertionError))
        broker = Broker(object(), hub=object())
        broker.connection = connection
        broker.channel = SimpleNamespace(set_qos=AsyncMock(), close=AsyncMock())
        consumer = await broker.consume(queue)
        queue.consume.assert_awaited_once_with(consumer.received, no_ack=False, robust=False)
        broker.channel.set_qos.assert_awaited_once_with(prefetch_count=1)
        assert await consumer.get(fail=False, timeout=1) is None
        message = SimpleNamespace(ack=AsyncMock(), nack=AsyncMock())
        await consumer.received(message)
        assert consumer.messages.qsize() == 1
        overflow = SimpleNamespace(nack=AsyncMock())
        await consumer.received(overflow)
        overflow.nack.assert_awaited_once_with(requeue=True)
        assert await consumer.wait(asyncio.Event(), 0.01)
        assert await consumer.get() is message
        message.ack.assert_not_awaited()
        message.nack.assert_not_awaited()
        assert not consumer.wakeup.event.is_set()
        queue.get.assert_not_called()
        await broker.close()
        assert not callbacks and consumer.closed
        broker.channel.close.assert_awaited_once()

    asyncio.run(verify())


def test_reconnection_wakes_and_invalidates_old_unacked_buffer():
    async def verify():
        connection = SimpleNamespace(reconnect_callbacks=set())
        consumer = await PushConsumer(connection, prefetch=1).start(
            SimpleNamespace(consume=AsyncMock()),
        )
        await consumer.received(SimpleNamespace(ack=AsyncMock()))
        consumer.reconnected()
        assert await consumer.wait(asyncio.Event(), 0.01)
        with pytest.raises(RuntimeError):
            await consumer.get()
        late = SimpleNamespace(nack=AsyncMock())
        await consumer.received(late)
        late.nack.assert_awaited_once_with(requeue=True)
        consumer.close()
        assert consumer.messages.empty() and not connection.reconnect_callbacks

    asyncio.run(verify())


def test_registration_failure_removes_connection_callback():
    async def verify():
        connection = SimpleNamespace(reconnect_callbacks=set())
        consumer = PushConsumer(connection, prefetch=1)
        with pytest.raises(TimeoutError):
            await consumer.start(SimpleNamespace(consume=AsyncMock(side_effect=TimeoutError)))
        assert consumer.closed and not connection.reconnect_callbacks

    asyncio.run(verify())
