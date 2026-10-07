"""进程内登录持锁执行门：一名执行者、两名最多等待250ms的前台请求。"""

import asyncio
from contextlib import asynccontextmanager

from services.common.errors import ErrorCode
from services.common.http import ApiError


class LoginBusy(ApiError):
    """仅标识本地执行门或命名锁繁忙，不代表下游限流。"""


def busy():
    return LoginBusy(429, ErrorCode.RATE_LIMITED, "登录正在处理，请稍后查询结果",
                     True, retry_after_seconds=3)


class LoginGate:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.waiters = 0

    @asynccontextmanager
    async def enter(self, *, background=False):
        if self.lock.locked() or self.waiters:
            if background or self.waiters >= 2:
                raise busy()
            self.waiters += 1
            try:
                async with asyncio.timeout(0.25):
                    await self.lock.acquire()
            except TimeoutError:
                raise busy() from None
            finally:
                self.waiters -= 1
        else:
            await self.lock.acquire()
        try:
            yield
        finally:
            self.lock.release()
