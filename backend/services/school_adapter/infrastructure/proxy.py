"""易代理短租约：Redis 跨进程共享，提取时间计入有效期。"""

import asyncio
import ipaddress
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from services.common.errors import ErrorCode
from services.common.http import ApiError

LEASE_KEY = "school_adapter:proxy:lease"
LOCK_KEY = "school_adapter:proxy:fetch_lock"
RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""
PUBLISH = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'PX', ARGV[3])
return 1
"""


@dataclass(frozen=True)
class ProxySettings:
    api_url: str = field(repr=False)
    secret: str = field(repr=False)

    @classmethod
    def from_env(cls):
        api_url = os.environ.get("ELECT_SCHOOL_PROXY_API_URL", "")
        secret = os.environ.get("ELECT_SCHOOL_PROXY_SECRET", "")
        try:
            parsed = httpx.URL(api_url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.host
                or parsed.username
                or parsed.password
                or parsed.fragment
                or not secret.strip()
            ):
                raise ValueError()
        except (ValueError, httpx.InvalidURL):
            raise ApiError(
                503, ErrorCode.DEPENDENCY_UNAVAILABLE, "学校代理配置不可用", True
            ) from None
        return cls(api_url, secret)


@dataclass(frozen=True)
class ProxyLease:
    """时间字段是 UTC Unix 时间戳，单位为秒。"""

    url: str
    acquired_at: float
    expires_at: float
    _token: str = field(default_factory=lambda: secrets.token_urlsafe(16), repr=False)

    def serialize(self):
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)


class ProxyPool:
    def __init__(self, store, settings, *, transport=None, clock=time.time):
        self.store, self.settings, self.transport, self.clock = store, settings, transport, clock

    async def get(self, deadline):
        try:
            async with asyncio.timeout(deadline.remaining()):
                return await self._get(deadline)
        except TimeoutError:
            raise ApiError(
                503, ErrorCode.DEPENDENCY_UNAVAILABLE, "学校代理暂时不可用", True
            ) from None

    async def _get(self, deadline):
        while True:
            lease = await self._cached()
            if lease:
                return lease

            token = secrets.token_urlsafe(24)
            if not await self.store.call("set", LOCK_KEY, token, nx=True, ex=8):
                await asyncio.sleep(min(0.1, deadline.remaining()))
                continue
            try:
                # 取得锁后重新读取，避免在等待锁期间重复提取。
                lease = await self._cached()
                if lease:
                    return lease
                lease = await self._fetch(deadline)
                ttl_ms = int((lease.expires_at - self.clock()) * 1000)
                if ttl_ms <= 0 or not await self.store.call(
                    "eval", PUBLISH, 2, LOCK_KEY, LEASE_KEY, token, lease.serialize(), ttl_ms
                ):
                    raise ApiError(
                        503, ErrorCode.DEPENDENCY_UNAVAILABLE, "学校代理暂时不可用", True
                    )
                return lease
            finally:
                await self.store.call("eval", RELEASE, 1, LOCK_KEY, token)

    async def _cached(self):
        value = await self.store.call("get", LEASE_KEY)
        if not value:
            return None
        try:
            lease = ProxyLease(**json.loads(value))
            return lease if lease.expires_at > self.clock() else None
        except (TypeError, ValueError):
            raise ApiError(
                503, ErrorCode.DEPENDENCY_UNAVAILABLE, "学校代理缓存异常", True
            ) from None

    async def _fetch(self, deadline):
        acquired_at = self.clock()
        url = httpx.URL(self.settings.api_url).copy_merge_params({"secret": self.settings.secret})
        timeout = min(5, deadline.remaining())
        request = httpx.Request(
            "GET", url,
            extensions={"timeout": dict.fromkeys(("connect", "read", "write", "pool"), timeout)},
        )
        try:
            async with asyncio.timeout(timeout):
                async with self.transport or httpx.AsyncHTTPTransport(trust_env=False) as transport:
                    response = await transport.handle_async_request(request)
                    try:
                        if response.status_code != 200:
                            raise ValueError()
                        chunks, size = [], 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 65536:
                                raise ValueError()
                            chunks.append(chunk)
                    finally:
                        await response.aclose()
            data = json.loads(b"".join(chunks))
            items = data["data"]
            if data["status"] != "success" or not isinstance(items, list) or len(items) != 1:
                raise ValueError()
            item = items[0]
            if not isinstance(item["ip"], str) or type(item["port"]) is not int:
                raise ValueError()
            address, port = ipaddress.IPv4Address(item["ip"]), item["port"]
            if not address.is_global or not 1 <= port <= 65535:
                raise ValueError()
            expiry = item.get("expire_time")
            if expiry is None or expiry == "":
                expires_at = acquired_at + 60
            else:
                expiry = datetime.fromisoformat(expiry)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone(timedelta(hours=8)))
                expires_at = expiry.timestamp()
        except (httpx.HTTPError, TimeoutError, KeyError, TypeError, ValueError):
            raise ApiError(
                503, ErrorCode.DEPENDENCY_UNAVAILABLE, "学校代理暂时不可用", True
            ) from None
        return ProxyLease(f"http://{address}:{port}", acquired_at, expires_at)

    async def invalidate(self, lease):
        await self.store.call("eval", RELEASE, 1, LEASE_KEY, lease.serialize())
