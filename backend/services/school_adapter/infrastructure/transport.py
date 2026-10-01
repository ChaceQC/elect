"""逐跳检查固定学校出口；每个操作共享一个单调时钟预算。"""

import asyncio
import json
import time
from urllib.parse import urljoin, urlsplit

import httpx

from services.common.errors import ErrorCode
from services.common.http import ApiError

from .dns import DestinationResolver, PinnedTransport

HOSTS = {"rz.hbue.edu.cn", "sdgl.hbue.edu.cn"}
UA = "Mozilla/5.0 (compatible; ELECT/0.3)"


class Deadline:
    def __init__(self, seconds):
        self.end = time.monotonic() + seconds

    def remaining(self):
        seconds = self.end - time.monotonic()
        if seconds <= 0:
            raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "学校请求超时", True)
        return seconds


async def check_destination(url, *, resolve=True, resolver=None):
    parsed = urlsplit(str(url))
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        raise ApiError(502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "学校跳转地址不受支持")
    if resolve:
        await (resolver or DestinationResolver()).resolve(parsed.hostname)


def parse_json(response, *, authenticated=False, check_code=True, allow_text_json=False):
    mime = response.headers.get("content-type", "").lower()
    if "json" not in mime and not (allow_text_json and mime.startswith("text/plain")):
        code = (
            ErrorCode.SCHOOL_REAUTH_REQUIRED if authenticated else ErrorCode.SCHOOL_PROTOCOL_CHANGED
        )
        raise ApiError(
            409 if authenticated else 502,
            code,
            "学校认证需要修复" if authenticated else "学校响应格式已变化",
        )
    try:
        value = json.loads(response.content, parse_float=str)
        if not isinstance(value, dict):
            raise ValueError()
    except ValueError:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校响应无法解析") from None
    code = value.get("code")
    if check_code and code is not None and (type(code) is not int or code != 200):
        if code in (401, 403):
            raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校认证需要修复")
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校业务请求未成功")
    return value


class SchoolTransport:
    def __init__(self, limiter, *, transport=None, resolve=True):
        self.limiter, self.transport, self.resolve = limiter, transport, resolve
        self.resolver = DestinationResolver()

    def client(self):
        return httpx.AsyncClient(
            transport=self.transport or PinnedTransport(self.resolver),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": UA},
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )

    async def request(
        self, client, method, url, deadline, *, authenticated=False, read_timeout=12, **kwargs
    ):
        try:
            async with asyncio.timeout(deadline.remaining()):
                return await self._request(
                    client, method, url, deadline, authenticated, read_timeout, kwargs
                )
        except (TimeoutError, httpx.TimeoutException):
            raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "学校请求超时", True) from None
        except httpx.HTTPError:
            raise ApiError(503, ErrorCode.SCHOOL_UNAVAILABLE, "学校连接暂时不可用", True) from None

    async def _request(self, client, method, url, deadline, authenticated, read_timeout, kwargs):
        origin = urlsplit(str(url)).hostname
        for hop in range(7):
            await check_destination(url, resolve=self.resolve, resolver=self.resolver)
            timeout = httpx.Timeout(min(read_timeout, deadline.remaining()), connect=3, pool=2)
            async with self.limiter.global_slot(deadline):
                async with client.stream(method, url, timeout=timeout, **kwargs) as response:
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 2 * 1024 * 1024:
                            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校响应过大")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    headers = dict(response.headers)
                    # aiter_bytes 已解压，不能让复制的 Response 再次解压同一内容。
                    headers.pop("content-encoding", None)
                    headers.pop("content-length", None)
                    result = httpx.Response(
                        response.status_code,
                        headers=headers,
                        content=content,
                        request=response.request,
                    )
            if result.is_redirect:
                if method != "GET" or authenticated or hop == 6:
                    raise ApiError(
                        409 if authenticated else 502,
                        ErrorCode.SCHOOL_REAUTH_REQUIRED
                        if authenticated
                        else ErrorCode.SCHOOL_PROTOCOL_CHANGED,
                        "学校认证跳转异常",
                    )
                target = urljoin(str(result.url), result.headers.get("location", ""))
                await check_destination(target, resolve=self.resolve, resolver=self.resolver)
                if (
                    "Authorization" in kwargs.get("headers", {})
                    and urlsplit(target).hostname != origin
                ):
                    raise ApiError(502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "学校跳转不受支持")
                url, kwargs = target, {}
                continue
            if result.status_code == 429:
                delay = result.headers.get("retry-after", "30")
                seconds = min(3600, max(1, int(delay))) if delay.isdigit() else 30
                raise ApiError(
                    429,
                    ErrorCode.RATE_LIMITED,
                    "学校请求频率受限，请稍后重试",
                    True,
                    retry_after_seconds=seconds,
                )
            if authenticated and result.status_code in (401, 403):
                raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校认证需要修复")
            if not 200 <= result.status_code < 300:
                raise ApiError(503, ErrorCode.SCHOOL_UNAVAILABLE, "学校系统暂时不可用", True)
            return result
