"""共享原子状态；Redis 失败时不降级到进程字典。"""

import asyncio
import hashlib
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError

from services.common.errors import ErrorCode
from services.common.http import ApiError

from .transport import Deadline

SWAP = """
local old = redis.call('GET', KEYS[1])
if old then redis.call('DEL', ARGV[1] .. old) end
redis.call('SET', KEYS[1], ARGV[2], 'EX', 120)
return 1
"""
PUBLISH = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', 120)
return 1
"""
CONSUME = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return false end
local value = redis.call('GET', KEYS[2])
redis.call('DEL', KEYS[1], KEYS[2])
return value
"""
RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""
SLOT = """
local t = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= 5 then return 0 end
if ARGV[2] == 'background' and redis.call('ZCARD', KEYS[2]) >= 4 then return 0 end
redis.call('ZADD', KEYS[1], now + 90000, ARGV[1])
if ARGV[2] == 'background' then redis.call('ZADD', KEYS[2], now + 90000, ARGV[1]) end
redis.call('PEXPIRE', KEYS[1], 100000)
redis.call('PEXPIRE', KEYS[2], 100000)
return 1
"""
RATE = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""


class SharedStore:
    def __init__(self, redis, crypto):
        self.redis, self.crypto = redis, crypto

    async def call(self, method, *args, **kwargs):
        try:
            return await getattr(self.redis, method)(*args, **kwargs)
        except RedisError:
            raise ApiError(
                503, ErrorCode.DEPENDENCY_UNAVAILABLE, "认证缓存暂时不可用，请稍后重试", True
            ) from None

    async def rate(self, category, key, *, limit=5, window=60):
        count = await self.call("eval", RATE, 1, f"school_adapter:rate:{category}:{key}", window)
        if count > limit:
            raise ApiError(
                429,
                ErrorCode.RATE_LIMITED,
                "请求过于频繁，请稍后重试",
                True,
                retry_after_seconds=window,
            )

    @asynccontextmanager
    async def global_slot(self, deadline, *, pool="interactive"):
        if await self.call("exists", "school_adapter:cooldown"):
            raise ApiError(
                429,
                ErrorCode.RATE_LIMITED,
                "学校请求频率受限，请稍后重试",
                True,
                retry_after_seconds=30,
            )
        token, key = secrets.token_urlsafe(24), "school_adapter:global_slots"
        background_key = "school_adapter:background_slots"
        while not await self.call("eval", SLOT, 2, key, background_key, token, pool):
            await asyncio.sleep(min(0.1, deadline.remaining()))
        try:
            yield
        finally:
            await self.call("zrem", key, token)
            await self.call("zrem", background_key, token)

    async def block(self, seconds):
        await self.call("set", "school_adapter:cooldown", "rate_limited", ex=seconds)

    @asynccontextmanager
    async def account_lock(self, alias, *, deadline=None):
        deadline = deadline or Deadline(5)
        key, token = f"school_adapter:account_lock:{alias}", secrets.token_urlsafe(24)
        while not await self.call("set", key, token, nx=True, ex=110):
            try:
                await asyncio.sleep(min(0.1, deadline.remaining()))
            except ApiError:
                raise ApiError(
                    429,
                    ErrorCode.RATE_LIMITED,
                    "该账号正在认证，请稍后重试",
                    True,
                    retry_after_seconds=3,
                ) from None
        try:
            yield
        finally:
            await self.call("eval", RELEASE, 1, key, token)

    async def put_secret(self, key, value, *, ttl=900):
        await self.call("set", key, self.crypto.seal(value, key), ex=ttl)

    async def get_secret(self, key):
        value = await self.call("get", key)
        return self.crypto.open(value, key) if value else None

    async def create_challenge(self, nonce_hash, protocol):
        deadline = Deadline(30)
        try:
            async with asyncio.timeout(deadline.remaining()):
                return await self._create_challenge(nonce_hash, protocol, deadline)
        except TimeoutError:
            raise ApiError(
                504, ErrorCode.SCHOOL_TIMEOUT, "验证码请求超时，请重新取图", True
            ) from None

    async def _create_challenge(self, nonce_hash, protocol, deadline):
        await self.rate("captcha", nonce_hash)
        challenge_id = secrets.token_urlsafe(32)
        pointer = f"school_adapter:browser:{nonce_hash}"
        prefix = "school_adapter:challenge:"
        # 在访问学校前作废旧图；乱序完成者不能发布自己的会话。
        await self.call("eval", SWAP, 1, pointer, prefix, challenge_id)
        challenge = await protocol.challenge(deadline=deadline)
        value = self.crypto.seal(
            {"uid": challenge.uid, "cookies": challenge.cookies, "nonce_hash": nonce_hash},
            prefix + challenge_id,
        )
        if not await self.call(
            "eval", PUBLISH, 2, pointer, prefix + challenge_id, challenge_id, value
        ):
            raise ApiError(400, ErrorCode.CAPTCHA_EXPIRED, "验证码已刷新，请使用最新图片")
        return {
            "challenge_id": challenge_id,
            "image_data_url": challenge.image,
            "expires_at": datetime.now(UTC) + timedelta(seconds=120),
        }

    async def consume_challenge(self, nonce_hash, challenge_id):
        if not isinstance(challenge_id, str) or not 43 <= len(challenge_id) <= 128:
            raise ApiError(400, ErrorCode.CAPTCHA_INVALID, "验证码标识无效")
        pointer, key = (
            f"school_adapter:browser:{nonce_hash}",
            f"school_adapter:challenge:{challenge_id}",
        )
        value = await self.call("eval", CONSUME, 2, pointer, key, challenge_id)
        if not value:
            raise ApiError(400, ErrorCode.CAPTCHA_EXPIRED, "验证码已过期或已提交，请重新取图")
        result = self.crypto.open(value, key)
        if result["nonce_hash"] != nonce_hash:
            raise ApiError(400, ErrorCode.CAPTCHA_INVALID, "验证码不属于当前浏览器")
        return result


def browser_hash(nonce):
    if not isinstance(nonce, str) or len(nonce) != 43:
        raise ApiError(400, ErrorCode.CAPTCHA_EXPIRED, "请先获取学校验证码")
    return hashlib.sha256(nonce.encode()).hexdigest()
