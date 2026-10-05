"""可中断的进程内提示与有界退避；持久扫描始终保留。"""

import asyncio
import random


class Wakeup:
    def __init__(self):
        self.event = asyncio.Event()

    def set(self):
        self.event.set()

    async def wait(self, stop, seconds):
        tasks = [asyncio.create_task(value.wait()) for value in (stop, self.event)]
        try:
            done, _ = await asyncio.wait(
                tasks, timeout=seconds, return_when=asyncio.FIRST_COMPLETED,
            )
            signalled = tasks[1] in done
            if signalled:
                self.event.clear()
            return signalled
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


class IdleBackoff:
    def __init__(self, steps=(1, 2, 5, 10)):
        self.steps, self.index = steps, 0

    def reset(self):
        self.index = 0

    def next(self, activity=False):
        if activity:
            self.reset()
            return 0
        delay = self.steps[self.index]
        self.index = min(self.index + 1, len(self.steps) - 1)
        return delay


def retry_delay(attempt, maximum=30):
    return min(maximum, 2 ** min(attempt, 5)) + random.uniform(0, 1)
