import asyncio

import httpx
import pytest
from test_school_proxy import SETTINGS, Clock, FakeStore

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.school_adapter.infrastructure.proxy import FAILURE_KEY, LEASE_KEY, LOCK_KEY, ProxyPool
from services.school_adapter.infrastructure.transport import Deadline


def test_concurrent_failure_is_shared_until_backoff_expires():
    async def run():
        clock = Clock()
        store = FakeStore(clock)
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def provider(request):
            calls.append(clock())
            if len(calls) == 1:
                started.set()
                await release.wait()
                return httpx.Response(503)
            return httpx.Response(200, json={
                "status": "success", "data": [{"ip": "8.8.8.8", "port": 8080}],
            })

        transport = httpx.MockTransport(provider)
        pools = [ProxyPool(store, SETTINGS, transport=transport, clock=clock) for _ in range(4)]
        tasks = [asyncio.create_task(pool.get(Deadline(1))) for pool in pools]
        await started.wait()
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert len(calls) == 1
        assert all(
            isinstance(result, ApiError)
            and (result.status, result.code, result.retryable)
            == (503, ErrorCode.DEPENDENCY_UNAVAILABLE, True)
            for result in results
        )
        assert store.read(LEASE_KEY) is None
        assert store.values[FAILURE_KEY] == ("1", clock() + 5)

        clock.now += 4.9
        with pytest.raises(ApiError) as caught:
            await pools[0].get(Deadline(1))
        assert caught.value.retry_after_seconds == 5
        assert len(calls) == 1
        assert store.values[FAILURE_KEY][1] == calls[0] + 5

        clock.now = calls[0] + 5
        lease = await pools[0].get(Deadline(1))
        assert len(calls) == 2
        assert lease.expires_at == calls[1] + 60
        store.values[FAILURE_KEY] = ("1", clock() + 5)
        assert await pools[1].get(Deadline(1)) == lease
        assert store.values[LEASE_KEY][1] == lease.expires_at

    asyncio.run(run())


@pytest.mark.parametrize("cancel_caller", [False, True])
def test_interrupted_fetch_leaves_waiters_in_backoff(cancel_caller):
    async def run():
        clock = Clock()
        store = FakeStore(clock)
        started = asyncio.Event()
        calls = []

        async def provider(request):
            calls.append(clock())
            started.set()
            await asyncio.sleep(1)

        pool = ProxyPool(store, SETTINGS, transport=httpx.MockTransport(provider), clock=clock)
        owner = asyncio.create_task(pool.get(Deadline(0.04 if not cancel_caller else 1)))
        await started.wait()
        waiters = [asyncio.create_task(pool.get(Deadline(1))) for _ in range(3)]
        await asyncio.sleep(0)
        if cancel_caller:
            owner.cancel()
            with pytest.raises(asyncio.CancelledError):
                await owner
        else:
            with pytest.raises(ApiError) as caught:
                await owner
            assert caught.value.status == 503 and caught.value.retryable
        results = await asyncio.gather(*waiters, return_exceptions=True)
        assert len(calls) == 1
        assert all(
            isinstance(result, ApiError)
            and result.status == 503
            and result.retry_after_seconds == 5
            for result in results
        )
        assert store.values[FAILURE_KEY] == ("1", clock() + 5)
        assert store.read(LOCK_KEY) is None

    asyncio.run(run())


def test_lost_lock_cannot_publish_failed_fetch_or_release_new_owner():
    async def run():
        clock = Clock()
        store = FakeStore(clock)

        async def provider(request):
            clock.now += 9
            store.values[LOCK_KEY] = ("next-owner", clock() + 8)
            return httpx.Response(503)

        pool = ProxyPool(store, SETTINGS, transport=httpx.MockTransport(provider), clock=clock)
        with pytest.raises(ApiError):
            await pool.get(Deadline(1))
        assert store.read(FAILURE_KEY) is None
        assert store.read(LOCK_KEY) == "next-owner"

    asyncio.run(run())


def test_cache_error_after_lock_does_not_record_supplier_failure():
    class CorruptCacheOnLock(FakeStore):
        async def call(self, method, *args, **kwargs):
            result = await super().call(method, *args, **kwargs)
            if method == "set" and result:
                self.values[LEASE_KEY] = ("{", self.clock() + 10)
            return result

    async def run():
        clock = Clock()
        store = CorruptCacheOnLock(clock)
        calls = []
        pool = ProxyPool(
            store, SETTINGS,
            transport=httpx.MockTransport(lambda request: calls.append(request)), clock=clock,
        )
        for _ in range(2):
            with pytest.raises(ApiError) as caught:
                await pool.get(Deadline(1))
            assert caught.value.message == "学校代理缓存异常"
            assert store.read(FAILURE_KEY) is None
        assert calls == []
        assert store.read(LOCK_KEY) is None

    asyncio.run(run())


def test_budget_exhausted_before_fetch_does_not_record_supplier_failure():
    class ElapsedDeadline:
        def __init__(self):
            self.calls = 0

        def remaining(self):
            self.calls += 1
            if self.calls == 1:
                return 1
            raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "学校请求超时", True)

    async def run():
        clock = Clock()
        store = FakeStore(clock)
        calls = []
        pool = ProxyPool(
            store, SETTINGS,
            transport=httpx.MockTransport(lambda request: calls.append(request)), clock=clock,
        )
        with pytest.raises(ApiError) as caught:
            await pool.get(ElapsedDeadline())
        assert caught.value.status == 504
        assert calls == []
        assert store.read(FAILURE_KEY) is None
        assert store.read(LOCK_KEY) is None

    asyncio.run(run())
