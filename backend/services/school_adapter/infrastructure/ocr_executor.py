"""计算槽由执行器拥有；取消调用者不会取消或释放正在运行的原生计算。"""

import asyncio
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from services.common.errors import ErrorCode
from services.common.http import ApiError


class OcrExecutor:
    def __init__(self, solver):
        self.solver = solver
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="school-ocr")
        self.waiting = deque()
        self.worker = None
        self.accepting = True
        self.active_deadline = None
        self.fatal = asyncio.Event()

    def request_stop(self):
        self.accepting = False

    def health_failure(self):
        if self.fatal.is_set():
            return "OCR_DRAIN_EXHAUSTED"
        if self.active_deadline is not None and time.monotonic() >= self.active_deadline + 5:
            return "OCR_COMPUTATION_STALLED"
        return None

    async def solve(self, image, deadline):
        if not self.accepting or len(self.waiting) >= 2:
            raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE,
                           "自动识别繁忙，请稍后重试", True, retry_after_seconds=3)
        remaining = deadline.remaining()
        future = asyncio.get_running_loop().create_future()
        future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        job = (image, deadline, future)
        if self.worker is None:
            self.worker = asyncio.create_task(self._run(job))
        else:
            self.waiting.append(job)
        try:
            async with asyncio.timeout(remaining):
                return await future
        finally:
            # 排队者取消即移出；真实计算仍由worker等待其Future。
            if job in self.waiting:
                self.waiting.remove(job)

    async def _run(self, job):
        try:
            while job:
                image, deadline, future = job
                if not future.done():
                    try:
                        self.active_deadline = time.monotonic() + deadline.remaining()
                        value = await asyncio.wrap_future(self.pool.submit(self.solver, image))
                    except Exception as error:
                        if not future.done():
                            future.set_exception(error)
                    else:
                        if not future.done():
                            future.set_result(value)
                    finally:
                        self.active_deadline = None
                job = self.waiting.popleft() if self.waiting else None
        finally:
            self.worker = None

    async def close(self, timeout=5):
        self.request_stop()
        while self.waiting:
            _, _, future = self.waiting.popleft()
            if not future.done():
                future.set_exception(ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE,
                                              "自动识别正在停止", True))
        try:
            if self.worker:
                async with asyncio.timeout(timeout):
                    await asyncio.shield(self.worker)
        except TimeoutError:
            self.fatal.set()
        finally:
            self.pool.shutdown(wait=False, cancel_futures=True)
        return not self.fatal.is_set()
