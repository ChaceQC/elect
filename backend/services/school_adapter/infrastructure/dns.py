"""校验并固定实际连接 IP；透明代理的虚拟 DNS 用固定 HTTPS DoH 解析。"""

import asyncio
import ipaddress
import socket
import time

import httpx

from services.common.errors import ErrorCode
from services.common.http import ApiError

BENCHMARK_NET = ipaddress.ip_network("198.18.0.0/15")


class DestinationResolver:
    def __init__(self):
        self.cache = {}

    async def resolve(self, host):
        cached = self.cache.get(host)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        try:
            answers = await asyncio.get_running_loop().getaddrinfo(
                host, 443, type=socket.SOCK_STREAM
            )
            addresses = [ipaddress.ip_address(item[4][0]) for item in answers]
            if addresses and all(address in BENCHMARK_NET for address in addresses):
                async with httpx.AsyncClient(
                    trust_env=False, timeout=5, follow_redirects=False
                ) as client:
                    response = await client.get(
                        "https://dns.google/resolve", params={"name": host, "type": "A"}
                    )
                    response.raise_for_status()
                    addresses = [
                        ipaddress.ip_address(item["data"])
                        for item in response.json().get("Answer", [])
                        if item.get("type") == 1
                    ]
            if not addresses or any(not address.is_global for address in addresses):
                raise ValueError()
            selected = str(
                next((address for address in addresses if address.version == 4), addresses[0])
            )
            self.cache[host] = selected, time.monotonic() + 60
            return selected
        except Exception:
            raise ApiError(503, ErrorCode.SCHOOL_UNAVAILABLE, "学校网络暂时不可用", True) from None


class PinnedTransport(httpx.AsyncBaseTransport):
    def __init__(self, resolver):
        self.resolver, self.transports = resolver, {}

    async def handle_async_request(self, request):
        host = request.url.host
        address = await self.resolver.resolve(host)
        if host not in self.transports:
            self.transports[host] = httpx.AsyncHTTPTransport(
                retries=0, trust_env=False, limits=httpx.Limits(max_connections=5)
            )
        wire = httpx.Request(
            request.method,
            request.url.copy_with(host=address),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": host},
        )
        return await self.transports[host].handle_async_request(wire)

    async def aclose(self):
        for transport in self.transports.values():
            await transport.aclose()
