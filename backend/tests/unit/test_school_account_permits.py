import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.school_adapter.infrastructure.redis_store import (
    ACCOUNT_DRAIN,
    ACCOUNT_READ,
    ACCOUNT_RELEASE,
    RELEASE,
    SharedStore,
)
from services.school_adapter.infrastructure.transport import Deadline


def test_account_read_registers_and_releases_each_holder():
    async def run():
        redis = SimpleNamespace(eval=AsyncMock(return_value=1))
        first, second = SharedStore(redis, None), SharedStore(redis, None)
        async with first.account_read("test", deadline=Deadline(1), balance=True):
            async with second.account_read("test", deadline=Deadline(1)):
                pass

        a, b, release_b, release_a = [call.args for call in redis.eval.await_args_list]
        keys = (
            "school_adapter:account_lock:test",
            "school_adapter:account_reads:test",
            "school_adapter:account_balances:test",
        )
        assert a[:5] == b[:5] == (ACCOUNT_READ, 3, *keys)
        assert a[5] != b[5] and (a[6], b[6]) == ("1", "0")
        assert release_b == (ACCOUNT_RELEASE, 2, *keys[1:], b[5])
        assert release_a == (ACCOUNT_RELEASE, 2, *keys[1:], a[5])

    asyncio.run(run())


def test_account_read_timeout_does_not_release_unacquired_permit():
    async def run():
        redis = SimpleNamespace(eval=AsyncMock(return_value=0))
        with pytest.raises(ApiError) as error:
            async with SharedStore(redis, None).account_read("test", deadline=Deadline(0)):
                pytest.fail("等待中的读取不应获得许可")
        assert error.value.code == ErrorCode.RATE_LIMITED
        assert redis.eval.await_count == 1
        assert redis.eval.await_args.args[0] == ACCOUNT_READ

    asyncio.run(run())


def test_cancelled_read_releases_its_permit():
    async def run():
        entered = asyncio.Event()
        redis = SimpleNamespace(eval=AsyncMock(return_value=1))

        async def read():
            async with SharedStore(redis, None).account_read(
                "test", deadline=Deadline(1), balance=True
            ):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(read())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        acquired, released = [call.args for call in redis.eval.await_args_list]
        assert released == (ACCOUNT_RELEASE, 2, *acquired[3:5], acquired[5])

    asyncio.run(run())


@pytest.mark.parametrize("cancel", [False, True])
def test_account_lock_releases_gate_if_drain_wait_stops(cancel):
    async def run():
        waiting = asyncio.Event()

        async def evaluate(script, *args):
            if script == ACCOUNT_DRAIN:
                waiting.set()
                return 0
            assert script == RELEASE
            return 1

        redis = SimpleNamespace(
            set=AsyncMock(return_value=True), eval=AsyncMock(side_effect=evaluate)
        )
        store = SharedStore(redis, None)

        async def lock():
            async with store.account_lock("test", deadline=Deadline(5 if cancel else 0)):
                pytest.fail("读取未排空时不能进入独占区")

        if cancel:
            task = asyncio.create_task(lock())
            await waiting.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(ApiError) as error:
                await lock()
            assert error.value.code == ErrorCode.RATE_LIMITED

        key, token = redis.set.await_args.args
        assert redis.set.await_args.kwargs == {"nx": True, "ex": 110}
        assert redis.eval.await_args.args == (RELEASE, 1, key, token)

    asyncio.run(run())


def test_account_lock_redis_failure_releases_gate_without_fallback():
    async def run():
        async def evaluate(script, *args):
            if script == ACCOUNT_DRAIN:
                raise RedisError("unavailable")
            assert script == RELEASE
            return 1

        redis = SimpleNamespace(
            set=AsyncMock(return_value=True), eval=AsyncMock(side_effect=evaluate)
        )
        with pytest.raises(ApiError) as error:
            async with SharedStore(redis, None).account_lock("test", deadline=Deadline(1)):
                pytest.fail("Redis 故障不能放行")
        assert error.value.code == ErrorCode.DEPENDENCY_UNAVAILABLE
        key, token = redis.set.await_args.args
        assert redis.eval.await_args.args == (RELEASE, 1, key, token)

    asyncio.run(run())
