import asyncio
import socket

import httpx
import pytest

from services.common.http import ApiError
from services.school_adapter.infrastructure.dns import DestinationResolver, PinnedTransport


def test_non_public_dns_address_is_rejected_before_connect(monkeypatch):
    async def run():
        async def private(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", private)
        with pytest.raises(ApiError):
            await DestinationResolver().resolve("rz.hbue.edu.cn")

    asyncio.run(run())


def test_pinned_connection_preserves_original_sni_host_and_cookie_scope():
    async def run():
        resolver = DestinationResolver()
        resolver.cache["rz.hbue.edu.cn"] = ("8.8.8.8", float("inf"))
        transport = PinnedTransport(resolver)

        def handler(request):
            assert request.url.host == "8.8.8.8"
            assert request.headers["host"] == "rz.hbue.edu.cn"
            assert request.extensions["sni_hostname"] == "rz.hbue.edu.cn"
            return httpx.Response(200, headers={"set-cookie": "CAS=synthetic; Path=/"})

        transport.transports["rz.hbue.edu.cn"] = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get("https://rz.hbue.edu.cn/authserver/login")
            assert response.url.host == "rz.hbue.edu.cn"
            assert next(iter(client.cookies.jar)).domain == "rz.hbue.edu.cn"

    asyncio.run(run())
