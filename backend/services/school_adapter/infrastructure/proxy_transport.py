"""学校请求共用短效代理；只读请求至多换一次出口，写入不重放。"""

import httpx

PROXY_ERRORS = (httpx.ProxyError, httpx.ConnectError, httpx.ConnectTimeout)


class RotatingProxyTransport(httpx.AsyncBaseTransport):
    def __init__(self, pool, *, factory=httpx.AsyncHTTPTransport):
        self.pool, self.factory, self.transports = pool, factory, {}

    async def handle_async_request(self, request):
        deadline = request.extensions["school_deadline"]
        retry = (
            request.method in {"GET", "HEAD"}
            and request.extensions.get("school_proxy_retry", False)
            and not deadline.proxy_retry_used
        )
        for attempt in range(2 if retry else 1):
            lease = await self.pool.get(deadline)
            key = lease.url, lease.acquired_at
            if key not in self.transports:
                self.transports[key] = self.factory(
                    proxy=lease.url, trust_env=False, retries=0,
                    limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
                )
            transport = self.transports[key]
            try:
                response = await transport.handle_async_request(request)
            except PROXY_ERRORS:
                await self.pool.invalidate(lease)
                if not retry or attempt:
                    raise
                deadline.proxy_retry_used = True
                continue
            if response.status_code == 407:
                await self.pool.invalidate(lease)
                if retry and not attempt:
                    await response.aclose()
                    deadline.proxy_retry_used = True
                    continue
            return response

    async def aclose(self):
        for transport in self.transports.values():
            await transport.aclose()
