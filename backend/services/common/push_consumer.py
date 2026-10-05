"""basic.consume推送到有界本地缓冲；业务提交/签名/ACK仍由领域负责。"""

import asyncio

from .scheduling import Wakeup


class PushConsumer:
    def __init__(self, connection, *, prefetch):
        self.connection = connection
        self.messages = asyncio.Queue(maxsize=prefetch)
        self.wakeup = Wakeup()
        self.invalid, self.closed = False, False

    async def start(self, queue):
        self.connection.reconnect_callbacks.add(self.reconnected)
        try:
            # 重连后显式重建channel/consumer，不能使用断线前的未ACK缓冲。
            await queue.consume(self.received, no_ack=False, robust=False)
        except BaseException:
            self.close()
            raise
        return self

    def reconnected(self, *_):
        self.invalid = True
        self.wakeup.set()

    async def received(self, message):
        if self.closed or self.invalid or self.messages.full():
            await message.nack(requeue=True)
            return
        self.messages.put_nowait(message)
        self.wakeup.set()

    async def get(self, *, fail=False, timeout=None):
        if self.invalid or self.closed:
            raise RuntimeError("消息消费连接须重建")
        try:
            message = self.messages.get_nowait()
        except asyncio.QueueEmpty:
            if fail:
                raise
            return None
        if self.messages.empty():
            self.wakeup.event.clear()
        return message

    async def wait(self, stop, seconds):
        return await self.wakeup.wait(stop, seconds)

    def close(self):
        self.closed = True
        self.connection.reconnect_callbacks.discard(self.reconnected)
        # Broker随后关闭channel，由MQ重排未ACK消息；不自行确认或丢弃持久任务。
        while not self.messages.empty():
            self.messages.get_nowait()
        self.wakeup.set()
