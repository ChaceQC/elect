import asyncio
import threading

import pytest

from services.common.http import ApiError
from services.school_adapter.infrastructure.ocr_executor import OcrExecutor
from services.school_adapter.infrastructure.transport import Deadline


def test_timeouts_queue_expiry_and_shutdown_never_overlap_real_solver():
    async def verify():
        entered, release = threading.Event(), threading.Event()
        active, peak, images = 0, 0, []

        def solver(image):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            images.append(image)
            entered.set()
            release.wait(3)
            active -= 1
            return "3"

        executor = OcrExecutor(solver)
        try:
            first = asyncio.create_task(executor.solve("first", Deadline(.08)))
            while not entered.is_set():
                await asyncio.sleep(.001)
            with pytest.raises(TimeoutError):
                await first
            with pytest.raises(TimeoutError):
                await executor.solve("expired", Deadline(.03))
            second = asyncio.create_task(executor.solve("second", Deadline(2)))
            third = asyncio.create_task(executor.solve("third", Deadline(2)))
            await asyncio.sleep(0)
            with pytest.raises(ApiError) as full:
                await executor.solve("overflow", Deadline(2))
            assert full.value.retryable
            assert images == ["first"] and active == peak == 1
            assert not await executor.close(timeout=.01)
            assert executor.fatal.is_set() and not executor.accepting
            for task in (second, third):
                with pytest.raises(ApiError):
                    await task
            release.set()
            await executor.worker
            assert peak == 1 and images == ["first"]
        finally:
            release.set()
            await executor.close()

    asyncio.run(verify())


def test_initialization_failure_is_retrieved_and_executor_can_continue():
    async def verify():
        attempts = 0

        def solver(image):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("synthetic initialization failure")
            return "4"

        executor = OcrExecutor(solver)
        try:
            with pytest.raises(RuntimeError):
                await executor.solve("first", Deadline(1))
            assert await executor.solve("second", Deadline(1)) == "4"
            assert await executor.close()
            assert not executor.fatal.is_set()
        finally:
            await executor.close()

    asyncio.run(verify())


def test_cancelled_waiter_does_not_release_running_slot():
    async def verify():
        entered, release = threading.Event(), threading.Event()
        images = []

        def solver(image):
            images.append(image)
            entered.set()
            release.wait(3)
            return "5"

        executor = OcrExecutor(solver)
        try:
            task = asyncio.create_task(executor.solve("cancelled", Deadline(2)))
            while not entered.is_set():
                await asyncio.sleep(.001)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            following = asyncio.create_task(executor.solve("following", Deadline(2)))
            await asyncio.sleep(0)
            assert images == ["cancelled"]
            release.set()
            assert await following == "5"
            assert images == ["cancelled", "following"]
        finally:
            release.set()
            await executor.close()

    asyncio.run(verify())
