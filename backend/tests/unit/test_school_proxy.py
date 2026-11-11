import asyncio

import httpx
import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.school_adapter.infrastructure.proxy import (
    FAILURE_KEY,
    LEASE_KEY,
    LOCK_KEY,
    PUBLISH,
    RELEASE,
    ProxyPool,
    ProxySettings,
)
from services.school_adapter.infrastructure.transport import Deadline


class Clock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        return self.now


class FakeStore:
    def __init__(self, clock):
        self.clock, self.values, self.published_ttls = clock, {}, []

    def read(self, key):
        value = self.values.get(key)
        if value and value[1] <= self.clock():
            del self.values[key]
            return None
        return value[0] if value else None

    async def call(self, method, *args, **kwargs):
        if method == "get":
            return self.read(args[0])
        if method == "set":
            key, value = args
            if kwargs.get("nx") and self.read(key):
                return False
            self.values[key] = (value, self.clock() + kwargs["ex"])
            return True
        script, _, *parts = args
        if script == RELEASE:
            key, expected = parts
            if self.read(key) == expected:
                del self.values[key]
                return 1
            return 0
        assert script == PUBLISH
        lock_key, lease_key, token, value, ttl_ms = parts
        if self.read(lock_key) != token:
            return 0
        self.published_ttls.append(ttl_ms)
        self.values[lease_key] = (value, self.clock() + ttl_ms / 1000)
        return 1


SETTINGS = ProxySettings(
    "https://api3.ydaili.cn/tools/BMeasureApi.ashx?orderId=synthetic-order"
    "&action=BEAPI&number=9&format=txt&type=3",
    "synthetic-secret",
)


@pytest.mark.parametrize(("endpoint", "query"), [
    (
        "MeasureApi.ashx",
        "orderId=synthetic-order&action=EAPI&number=9&format=txt&type=3"
        "&jsonMeta=0&extra=first&extra=second",
    ),
    (
        "BMeasureApi.ashx",
        "orderId=synthetic-order&action=BEAPI&number=9&format=txt&type=3"
        "&jsonMeta=0&extra=first&extra=second",
    ),
    ("MeasureApi.ashx", "orderId=synthetic-order"),
])
def test_shared_fetch_preserves_parameters_and_expires_from_request_start(endpoint, query):
    async def run():
        clock, calls = Clock(), []
        store = FakeStore(clock)

        async def provider(request):
            calls.append(clock())
            assert request.method == "GET"
            assert all(value == 5 for value in request.extensions["timeout"].values())
            assert request.url.path == f"/tools/{endpoint}"
            assert request.url.params.multi_items() == [
                *httpx.QueryParams(query).multi_items(), ("secret", "synthetic-secret"),
            ]
            await asyncio.sleep(0.02)
            clock.now += 4
            return httpx.Response(200, json={
                "status": "success", "data": [{"ip": "8.8.8.8", "port": 8080}],
            })

        transport = httpx.MockTransport(provider)
        settings = ProxySettings(
            f"https://api3.ydaili.cn/tools/{endpoint}?{query}",
            SETTINGS.secret,
        )
        pools = [ProxyPool(store, settings, transport=transport, clock=clock) for _ in range(4)]
        leases = await asyncio.gather(*(pool.get(Deadline(10)) for pool in pools))
        assert len(calls) == 1
        assert all(lease == leases[0] for lease in leases)
        lease = leases[0]
        assert lease.url == "http://8.8.8.8:8080"
        assert lease.acquired_at == calls[0]
        assert lease.expires_at == calls[0] + 60
        assert store.published_ttls == [56_000]
        assert store.values[LEASE_KEY][1] == lease.expires_at
        assert await pools[0].get(Deadline(10)) == lease
        clock.now = lease.expires_at
        assert (await pools[0].get(Deadline(10))).acquired_at == lease.expires_at
        assert len(calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize(("expiry", "lifetime"), [
    ("2023-11-15 06:13:50", 30),
    ("2023-11-15 06:15:20", 120),
    ("2023-11-14T22:15:20+00:00", 120),
])
def test_supplier_expiry_controls_lease_and_ttl(expiry, lifetime):
    async def run():
        clock, calls = Clock(), []
        store = FakeStore(clock)

        def provider(request):
            item = {"ip": "8.8.8.8", "port": 8080}
            if not calls:
                item["expire_time"] = expiry
            calls.append(clock())
            clock.now += 4
            return httpx.Response(200, json={"status": "success", "data": [item]})

        pool = ProxyPool(store, SETTINGS, transport=httpx.MockTransport(provider), clock=clock)
        lease = await pool.get(Deadline(1))
        assert lease.expires_at == calls[0] + lifetime
        assert store.published_ttls == [(lifetime - 4) * 1000]
        assert store.values[LEASE_KEY][1] == lease.expires_at
        assert await pool.get(Deadline(1)) == lease
        clock.now = lease.expires_at
        assert (await pool.get(Deadline(1))).acquired_at == lease.expires_at
        assert len(calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize("expiry", [None, ""])
def test_empty_supplier_expiry_falls_back_to_60_seconds(expiry):
    async def run():
        clock = Clock()
        store = FakeStore(clock)
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            "status": "success",
            "data": [{"ip": "8.8.8.8", "port": 8080, "expire_time": expiry}],
        }))
        pool = ProxyPool(store, SETTINGS, transport=transport, clock=clock)
        lease = await pool.get(Deadline(1))
        assert lease.expires_at == lease.acquired_at + 60

    asyncio.run(run())


def test_invalidation_compares_complete_lease_even_when_address_is_reused():
    async def run():
        clock = Clock()
        store = FakeStore(clock)
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            "status": "success", "data": [{"ip": "8.8.8.8", "port": 8080}],
        }))
        pool = ProxyPool(store, SETTINGS, transport=transport, clock=clock)
        old = await pool.get(Deadline(1))
        await pool.invalidate(old)
        new = await pool.get(Deadline(1))
        assert old.url == new.url and old != new
        await pool.invalidate(old)
        assert await pool.get(Deadline(1)) == new
        await pool.invalidate(new)
        assert store.read(LEASE_KEY) is None

    asyncio.run(run())


@pytest.mark.parametrize("response", [
    httpx.Response(503),
    httpx.Response(302, headers={"location": "https://example.invalid/"}),
    httpx.Response(200, text="synthetic-response"),
    httpx.Response(200, json={"status": "error", "data": []}),
    httpx.Response(200, json={"status": "success", "data": []}),
    httpx.Response(200, json={"status": "success", "data": [{"ip": "127.0.0.1", "port": 80}]}),
    httpx.Response(200, json={"status": "success", "data": [{"ip": "8.8.8.8", "port": "80"}]}),
    httpx.Response(200, json={"status": "success", "data": [
        {"ip": "8.8.8.8", "port": 8080, "expire_time": "2023-11-15 06:13:19"},
    ]}),
    httpx.Response(200, json={"status": "success", "data": [
        {"ip": "8.8.8.8", "port": 8080, "expire_time": "invalid-expiry"},
    ]}),
    httpx.Response(200, json={"status": "success", "data": [
        {"ip": "8.8.8.8", "port": 8080, "expire_time": 123},
    ]}),
    httpx.ConnectError("synthetic-secret synthetic-response"),
])
def test_supplier_failure_is_retryable_and_does_not_expose_request_or_response(response):
    async def run():
        clock = Clock()
        store = FakeStore(clock)
        def provider(request):
            if isinstance(response, Exception):
                raise response
            return response

        pool = ProxyPool(store, SETTINGS, transport=httpx.MockTransport(provider), clock=clock)
        with pytest.raises(ApiError) as caught:
            await pool.get(Deadline(1))
        assert (caught.value.status, caught.value.code, caught.value.retryable) == (
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, True,
        )
        assert "synthetic-secret" not in str(caught.value)
        assert "synthetic-response" not in str(caught.value)
        assert store.read(LOCK_KEY) is None
        assert store.read(LEASE_KEY) is None
        assert store.values[FAILURE_KEY] == ("1", clock() + 5)

    asyncio.run(run())


def test_caller_deadline_cancels_fetch_and_releases_lock():
    async def run():
        clock = Clock()
        store = FakeStore(clock)

        async def provider(request):
            await asyncio.sleep(1)

        pool = ProxyPool(store, SETTINGS, transport=httpx.MockTransport(provider), clock=clock)
        with pytest.raises(ApiError) as caught:
            await pool.get(Deadline(0.03))
        assert caught.value.status == 503 and caught.value.retryable
        assert store.read(LOCK_KEY) is None

    asyncio.run(run())


def test_expired_fetch_lock_cannot_publish_stale_lease():
    async def run():
        clock = Clock()
        store = FakeStore(clock)

        async def provider(request):
            clock.now += 9
            return httpx.Response(200, json={
                "status": "success", "data": [{"ip": "8.8.8.8", "port": 8080}],
            })

        pool = ProxyPool(store, SETTINGS, transport=httpx.MockTransport(provider), clock=clock)
        with pytest.raises(ApiError) as caught:
            await pool.get(Deadline(1))
        assert caught.value.status == 503 and caught.value.retryable
        assert store.read(LEASE_KEY) is None

    asyncio.run(run())


def test_settings_hide_values_and_reject_invalid_configuration(monkeypatch):
    monkeypatch.setenv("ELECT_SCHOOL_PROXY_API_URL", SETTINGS.api_url)
    monkeypatch.setenv("ELECT_SCHOOL_PROXY_SECRET", SETTINGS.secret)
    settings = ProxySettings.from_env()
    assert settings == SETTINGS
    assert SETTINGS.api_url not in repr(settings)
    assert SETTINGS.secret not in repr(settings)
    monkeypatch.setenv("ELECT_SCHOOL_PROXY_API_URL", "https://synthetic:password@example.com")
    with pytest.raises(ApiError) as caught:
        ProxySettings.from_env()
    assert caught.value.status == 503 and caught.value.retryable
    assert "password" not in str(caught.value)
