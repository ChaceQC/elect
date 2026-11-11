"""学校读取共享代理替换预算，同时保留原有的直连及上游重试。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.school_adapter.application.sessions import SchoolSessions
from services.school_adapter.infrastructure.protocol import SchoolProtocol
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
        self.invalidated.append(lease.url)
        self.index = 1


def proxied_sessions(pool, handler):
    def factory(**options):
        return httpx.MockTransport(lambda request: handler(options["proxy"], request))

    wire = RotatingProxyTransport(pool, factory=factory)
    transport = SchoolTransport(Limiter(), transport=wire, proxy_pool=pool)
    return SchoolSessions(None, None, SchoolProtocol(transport), None)


async def read(sessions):
    return await sessions.read_attempts(None, None, "/rooms", {}, "synthetic", {}, Deadline(2), 1)


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ConnectTimeout])
def test_continuous_proxy_connection_failure_uses_only_one_replacement(failure):
    async def verify():
        pool, calls = Pool(), []

        def handler(proxy, request):
            calls.append(proxy)
            raise failure("synthetic connection failure")

        with pytest.raises(ApiError) as result:
            await read(proxied_sessions(pool, handler))
        assert result.value.code == (
            ErrorCode.SCHOOL_TIMEOUT if failure is httpx.ConnectTimeout
            else ErrorCode.SCHOOL_UNAVAILABLE
        )
        assert calls == [lease.url for lease in pool.leases]
        assert pool.invalidated == calls

    asyncio.run(verify())


def test_proxy_replacement_followed_by_school_503_does_not_retry_again():
    async def verify():
        pool, calls = Pool(), []

        def handler(proxy, request):
            calls.append(proxy)
            if len(calls) == 1:
                raise httpx.ConnectError("synthetic connection failure")
            return httpx.Response(503)

        with pytest.raises(ApiError) as result:
            await read(proxied_sessions(pool, handler))
        assert result.value.code == ErrorCode.SCHOOL_UNAVAILABLE
        assert calls == [lease.url for lease in pool.leases]
        assert pool.invalidated == [pool.leases[0].url]

    asyncio.run(verify())


def test_school_503_retries_on_same_proxy():
    async def verify():
        pool, calls = Pool(), []

        def handler(proxy, request):
            calls.append(proxy)
            if len(calls) == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"code": 200})

        value, _ = await read(proxied_sessions(pool, handler))
        assert value == {"code": 200}
        assert calls == [pool.leases[0].url] * 2
        assert not pool.invalidated

    asyncio.run(verify())


def test_direct_connection_failure_still_retries():
    async def verify():
        calls = []

        def handler(request):
            calls.append(request.url)
            if len(calls) == 1:
                raise httpx.ConnectError("synthetic connection failure")
            return httpx.Response(200, json={"code": 200})

        transport = SchoolTransport(
            Limiter(), transport=httpx.MockTransport(handler), resolve=False
        )
        sessions = SchoolSessions(None, None, SchoolProtocol(transport), None)
        value, _ = await read(sessions)
        assert value == {"code": 200}
        assert len(calls) == 2

    asyncio.run(verify())
