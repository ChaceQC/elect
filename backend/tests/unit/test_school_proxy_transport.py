"""代理切换只重试读取；认证、绑定和支付写保持原发送边界。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from services.common.http import ApiError
from services.common.runtime import school_proxy_enabled
from services.school_adapter.infrastructure.payment_transport import PaymentTransport
from services.school_adapter.infrastructure.proxy_transport import RotatingProxyTransport
from services.school_adapter.infrastructure.transport import Deadline, SchoolTransport


class Limiter:
    @asynccontextmanager
    async def global_slot(self, deadline, **options):
        deadline.remaining()
        yield


class Pool:
    def __init__(self):
        self.leases = [
            SimpleNamespace(url="http://8.8.8.8:40001", acquired_at=1),
            SimpleNamespace(url="http://1.1.1.1:40002", acquired_at=2),
        ]
        self.index, self.invalidated = 0, []

    async def get(self, deadline):
        deadline.remaining()
        return self.leases[self.index]

    async def invalidate(self, lease):
        self.invalidated.append(lease)
        self.index = 1


def transport_for(pool, handler, options):
    def factory(**kwargs):
        options.append(kwargs)
        return httpx.MockTransport(lambda request: handler(kwargs["proxy"], request))

    return RotatingProxyTransport(pool, factory=factory)


@pytest.mark.parametrize("failure", [httpx.ProxyError, httpx.ConnectError, httpx.ConnectTimeout])
def test_failed_proxy_is_replaced_for_read_and_school_dns_is_not_required(failure):
    async def verify():
        pool, seen, options = Pool(), [], []

        def handler(proxy, request):
            seen.append((proxy, request.url.host, request.headers["authorization"]))
            if len(seen) == 1:
                raise failure("synthetic tunnel failure")
            return httpx.Response(200, json={"code": 200, "data": []})

        transport = SchoolTransport(
            Limiter(), proxy_pool=pool, transport=transport_for(pool, handler, options),
        )
        transport.resolver.resolve = AsyncMock(side_effect=AssertionError("local DNS used"))
        deadline = Deadline(2)
        async with transport.client() as client:
            result = await transport.request(
                client, "GET", "https://sdgl.hbue.edu.cn/api/getInfo", deadline,
                retry_proxy=True, authenticated=True,
                headers={"Authorization": "Bearer synthetic"},
            )
        assert result.status_code == 200 and len(seen) == 2
        assert [row[0] for row in seen] == [lease.url for lease in pool.leases]
        assert all(row[1:] == ("sdgl.hbue.edu.cn", "Bearer synthetic") for row in seen)
        assert pool.invalidated == [pool.leases[0]] and deadline.proxy_retry_used
        assert all(option["trust_env"] is False and option["retries"] == 0 for option in options)
        assert all("verify" not in option and "proxy_auth" not in option for option in options)

    asyncio.run(verify())


@pytest.mark.parametrize("kind", [SchoolTransport, PaymentTransport])
@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ProxyError])
def test_proxy_failure_never_replays_post(kind, failure):
    async def verify():
        pool, calls, options = Pool(), [], []

        def handler(proxy, request):
            calls.append(request)
            raise failure("synthetic unknown dispatch")

        transport = kind(
            Limiter(), proxy_pool=pool, transport=transport_for(pool, handler, options),
        )
        url = (
            "https://sdgl.hbue.edu.cn/api/base/order/phonePay" if kind is SchoolTransport
            else "http://cwcwx.hbue.edu.cn/zhifu/PayMain.aspx?prePayId=synthetic"
        )
        deadline = Deadline(2)
        with pytest.raises(ApiError):
            async with transport.client() as client:
                await transport.request(client, "POST", url, deadline, data={"synthetic": "1"})
        assert len(calls) == 1 and not deadline.proxy_retry_used
        assert pool.invalidated == ([pool.leases[0]] if failure is httpx.ProxyError else [])

    asyncio.run(verify())


@pytest.mark.parametrize("status", [401, 429, 502, 503, 504])
def test_school_response_keeps_proxy(status):
    async def verify():
        pool, options, calls = Pool(), [], []

        def handler(proxy, request):
            calls.append(proxy)
            return httpx.Response(status, text="synthetic")

        wire = transport_for(pool, handler, options)
        async with httpx.AsyncClient(transport=wire) as client:
            result = await client.get(
                "https://sdgl.hbue.edu.cn/api/getInfo",
                extensions={"school_deadline": Deadline(2), "school_proxy_retry": True},
            )
        assert result.status_code == status
        assert len(calls) == 1 and not pool.invalidated

    asyncio.run(verify())


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_proxy_407_retries_read_with_new_lease(method):
    async def verify():
        pool, options, calls, rejected = Pool(), [], [], []

        def handler(proxy, request):
            calls.append(proxy)
            if len(calls) == 1:
                response = httpx.Response(407, stream=httpx.ByteStream(b"synthetic"))
                rejected.append(response)
                return response
            return httpx.Response(200)

        wire = transport_for(pool, handler, options)
        deadline = Deadline(2)
        async with httpx.AsyncClient(transport=wire) as client:
            result = await client.request(
                method, "https://sdgl.hbue.edu.cn/api/getInfo",
                extensions={"school_deadline": deadline, "school_proxy_retry": True},
            )
        assert result.status_code == 200 and rejected[0].is_closed
        assert calls == [lease.url for lease in pool.leases]
        assert pool.invalidated == [pool.leases[0]] and deadline.proxy_retry_used

    asyncio.run(verify())


@pytest.mark.parametrize("failure", [
    httpx.ReadTimeout, httpx.WriteTimeout, httpx.ReadError, httpx.WriteError,
    httpx.RemoteProtocolError, httpx.PoolTimeout,
])
def test_non_proxy_failure_keeps_lease_and_propagates(failure):
    async def verify():
        pool, options, calls = Pool(), [], []

        def handler(proxy, request):
            calls.append(proxy)
            raise failure("synthetic upstream failure")

        wire = transport_for(pool, handler, options)
        deadline = Deadline(2)
        with pytest.raises(failure):
            async with httpx.AsyncClient(transport=wire) as client:
                await client.get(
                    "https://sdgl.hbue.edu.cn/api/getInfo",
                    extensions={"school_deadline": deadline, "school_proxy_retry": True},
                )
        assert calls == [pool.leases[0].url] and not pool.invalidated
        assert not deadline.proxy_retry_used

    asyncio.run(verify())


@pytest.mark.parametrize("failure", ["connection", "status"])
def test_final_proxy_failure_invalidates_latest_lease(failure):
    async def verify():
        pool, options, calls = Pool(), [], []

        def handler(proxy, request):
            calls.append(proxy)
            if failure == "connection":
                raise httpx.ConnectError("synthetic connection failure")
            return httpx.Response(407)

        wire = transport_for(pool, handler, options)
        deadline = Deadline(2)
        async with httpx.AsyncClient(transport=wire) as client:
            if failure == "connection":
                with pytest.raises(httpx.ConnectError):
                    await client.get(
                        "https://sdgl.hbue.edu.cn/api/getInfo",
                        extensions={"school_deadline": deadline, "school_proxy_retry": True},
                    )
            else:
                result = await client.get(
                    "https://sdgl.hbue.edu.cn/api/getInfo",
                    extensions={"school_deadline": deadline, "school_proxy_retry": True},
                )
                assert result.status_code == 407
        assert calls == [lease.url for lease in pool.leases]
        assert pool.invalidated == pool.leases and deadline.proxy_retry_used

    asyncio.run(verify())


def test_proxied_redirect_still_rejects_unregistered_target():
    async def verify():
        pool, options, calls = Pool(), [], []

        def handler(proxy, request):
            calls.append(request)
            return httpx.Response(302, headers={"location": "https://example.invalid/"})

        transport = SchoolTransport(
            Limiter(), proxy_pool=pool, transport=transport_for(pool, handler, options),
        )
        with pytest.raises(ApiError):
            async with transport.client() as client:
                await transport.request(
                    client, "GET", "https://rz.hbue.edu.cn/authserver/login", Deadline(2),
                    retry_proxy=True,
                )
        assert len(calls) == 1 and not pool.invalidated

    asyncio.run(verify())


@pytest.mark.parametrize("kind", [SchoolTransport, PaymentTransport])
def test_allowed_redirect_keeps_proxy_budget_and_reuses_the_same_ip(kind):
    async def verify():
        pool, calls, options = Pool(), [], []

        def handler(proxy, request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(302, headers={"location": (
                    "/authserver/kaptcha" if kind is SchoolTransport
                    else "/zhifu/PayMain.aspx?prePayId=synthetic"
                )})
            return httpx.Response(200, text="synthetic")

        transport = kind(
            Limiter(), proxy_pool=pool, transport=transport_for(pool, handler, options),
        )
        transport.resolver.resolve = AsyncMock(side_effect=AssertionError("local DNS used"))
        url = (
            "https://rz.hbue.edu.cn/authserver/login" if kind is SchoolTransport
            else "http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=synthetic"
        )
        async with transport.client() as client:
            response = await transport.request(client, "GET", url, Deadline(2))
        assert response.status_code == 200 and len(calls) == 2
        assert len(options) == 1 and not pool.invalidated

    asyncio.run(verify())


def test_proxy_stream_failure_keeps_the_same_lease():
    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial"
            raise httpx.ReadError("synthetic interrupted response")

    async def verify():
        pool, options = Pool(), []
        wire = transport_for(
            pool, lambda *_: httpx.Response(200, stream=BrokenStream()), options,
        )
        with pytest.raises(httpx.ReadError):
            async with httpx.AsyncClient(transport=wire) as client:
                await client.get(
                    "https://sdgl.hbue.edu.cn/api/getInfo",
                    extensions={"school_deadline": Deadline(2), "school_proxy_retry": True},
                )
        assert not pool.invalidated and len(options) == 1

    asyncio.run(verify())


def test_proxy_is_disabled_by_default_and_rejects_misspelled_flag(monkeypatch):
    monkeypatch.delenv("ELECT_SCHOOL_PROXY_ENABLED", raising=False)
    assert not school_proxy_enabled()
    monkeypatch.setenv("ELECT_SCHOOL_PROXY_ENABLED", "true")
    assert school_proxy_enabled()
    monkeypatch.setenv("ELECT_SCHOOL_PROXY_ENABLED", "tru")
    with pytest.raises(RuntimeError, match="true/false"):
        school_proxy_enabled()
