"""支付独立 CookieJar，逐跳限制地址且不重放 POST 重定向。"""

import asyncio
from urllib.parse import urljoin, urlsplit

import httpx

from services.common.errors import ErrorCode
from services.common.http import ApiError

from .dns import DestinationResolver, PinnedTransport
from .payment_protocol import check_pay_url
from .transport import UA


class PaymentTransport:
    def __init__(self, limiter, *, transport=None, resolve=True):
        self.limiter, self.transport, self.resolve = limiter, transport, resolve
        self.resolver = DestinationResolver()

    def client(self):
        return httpx.AsyncClient(
            transport=self.transport or PinnedTransport(self.resolver),
            trust_env=False,
            follow_redirects=False,
            headers={"User-Agent": UA},
        )

    async def request(self, client, method, url, deadline, **kwargs):
        try:
            async with asyncio.timeout(deadline.remaining()):
                return await self._request(client, method, url, deadline, kwargs)
        except (TimeoutError, httpx.HTTPError):
            raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "学校支付请求结果待确认", True) from None

    async def _request(self, client, method, url, deadline, kwargs):
        origin = urlsplit(str(url)).hostname
        for hop in range(7):
            parsed = check_pay_url(url)
            if parsed.hostname != origin:
                raise ApiError(502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "学校支付跨站跳转不受支持")
            if self.resolve:
                await self.resolver.resolve(parsed.hostname)
            async with self.limiter.global_slot(deadline, pool="background"):
                async with client.stream(
                    method,
                    url,
                    timeout=httpx.Timeout(min(15, deadline.remaining()), connect=3, pool=2),
                    **kwargs,
                ) as response:
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 2 * 1024 * 1024:
                            raise ApiError(
                                502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校支付响应过大"
                            )
                        chunks.append(chunk)
                    headers = dict(response.headers)
                    headers.pop("content-encoding", None)
                    headers.pop("content-length", None)
                    result = httpx.Response(
                        response.status_code,
                        headers=headers,
                        content=b"".join(chunks),
                        request=response.request,
                    )
            if result.is_redirect:
                if hop == 6 or method == "POST" and result.status_code in {307, 308}:
                    raise ApiError(502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "支付表单不能自动重发")
                url = urljoin(str(result.url), result.headers.get("location", ""))
                if method == "POST":
                    method = "GET"
                kwargs = {}
                continue
            if not result.is_success:
                raise ApiError(503, ErrorCode.SCHOOL_UNAVAILABLE, "学校支付页面暂时不可用", True)
            return result
