import asyncio
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.school_adapter.application.candidates import search_candidates
from services.school_adapter.application.room_filters import filter_choices
from services.school_adapter.infrastructure.redis_store import SharedStore
from services.school_adapter.infrastructure.transport import Deadline, SchoolTransport


def test_school_429_publishes_shared_cooldown_with_remaining_ttl():
    async def run():
        redis = SimpleNamespace(
            pttl=AsyncMock(side_effect=[-2, 11450, 0, -2]),
            eval=AsyncMock(return_value=1),
            zrem=AsyncMock(),
            set=AsyncMock(),
        )
        store = SharedStore(redis, None)
        transport = SchoolTransport(
            store,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, headers={"retry-after": "45"})
            ),
            resolve=False,
        )
        async with transport.client() as client:
            with pytest.raises(ApiError) as first:
                await transport.request(
                    client, "GET", "https://rz.hbue.edu.cn/", Deadline(1)
                )
        assert first.value.status == 429 and first.value.retry_after_seconds == 45
        redis.set.assert_awaited_once_with(
            "school_adapter:cooldown", "rate_limited", ex=45
        )
        with pytest.raises(ApiError) as blocked:
            async with store.global_slot(Deadline(1)):
                pass
        assert blocked.value.code == ErrorCode.RATE_LIMITED
        assert blocked.value.retry_after_seconds == 12
        for _ in range(2):  # TTL为0或键不存在时均可继续。
            async with store.global_slot(Deadline(1)):
                pass
        assert redis.eval.await_count == 3

    asyncio.run(run())


def test_rate_limit_uses_remaining_ttl_and_never_returns_zero():
    async def run():
        redis = SimpleNamespace(
            eval=AsyncMock(side_effect=[5, 6, 7, 8]),
            pttl=AsyncMock(side_effect=[1001, 1, -2]),
        )
        store = SharedStore(redis, None)
        await store.rate("login", "owner")
        for expected in [2, 1, 1]:
            with pytest.raises(ApiError) as error:
                await store.rate("login", "owner")
            assert error.value.status == 429
            assert error.value.retry_after_seconds == expected
        assert redis.pttl.await_count == 3

    asyncio.run(run())


def test_candidate_and_filter_limits_are_separate_per_owner():
    async def run():
        counters = Counter()
        windows = {}

        async def evaluate(script, num_keys, key, window):
            counters[key] += 1
            windows[key] = window
            return counters[key]

        redis = SimpleNamespace(eval=evaluate, pttl=AsyncMock(return_value=750))
        store = SharedStore(redis, None)
        sessions = SimpleNamespace(read=AsyncMock(return_value={
            "data": {"total": 0, "records": []},
        }))
        state = SimpleNamespace(school_store=store, school_sessions=sessions)
        principal = SimpleNamespace(user_id="owner-a", request_id="request")
        query = SimpleNamespace(page_size=20, page=1, q="", room_id=None)
        filters = SimpleNamespace(level="buildings")
        for _ in range(5):
            assert (await search_candidates(state, principal, query))["items"] == []
        with pytest.raises(ApiError) as search_limit:
            await search_candidates(state, principal, query)
        assert search_limit.value.status == 429
        for _ in range(10):
            assert (await filter_choices(state, principal, filters)).items == []
        with pytest.raises(ApiError) as filter_limit:
            await filter_choices(state, principal, filters)
        assert filter_limit.value.status == 429
        principal.user_id = "owner-b"
        await search_candidates(state, principal, query)
        assert sessions.read.await_count == 16
        assert set(windows.values()) == {1}

    asyncio.run(run())
