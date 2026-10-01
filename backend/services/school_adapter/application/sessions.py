import asyncio
import random
from contextlib import nullcontext
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.crypto import lookup_aliases
from ..infrastructure.ocr import solve_image
from ..infrastructure.transport import Deadline
from .token_cache import cache_token


class SchoolSessions:
    def __init__(self, repository, store, protocol, lookup, *, solver=solve_image):
        self.repository, self.store, self.protocol, self.lookup = (
            repository,
            store,
            protocol,
            lookup,
        )
        self.solver = solver
        self.ocr_lock = asyncio.Lock()

    async def background_auth(self, payload, deadline):
        # 两次取图、最多一次 A03；模型延迟加载并限制同进程推理并发。
        async with asyncio.timeout(deadline.remaining()):
            challenge = await self.protocol.challenge(deadline=deadline, pool="background")
            answer = None
            for attempt in range(2):
                async with self.ocr_lock:
                    try:
                        answer = await asyncio.to_thread(self.solver, challenge.image)
                    except Exception:
                        raise ApiError(
                            409,
                            ErrorCode.SCHOOL_REAUTH_REQUIRED,
                            "自动验证码识别不可用，请人工认证",
                        ) from None
                if answer is not None:
                    break
                if attempt == 0:
                    async with self.protocol.transport.client() as client:
                        from ..infrastructure.protocol import restore_cookies

                        restore_cookies(client, challenge.cookies)
                        challenge = await self.protocol.next_challenge(
                            client, challenge.uid, deadline, pool="background"
                        )
            if answer is None:
                raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校验证码需要人工认证")
            return await self.protocol.authenticate(
                payload["student_id"],
                payload["password"],
                {"uid": challenge.uid, "cookies": challenge.cookies},
                str(answer),
                deadline=deadline,
                pool="background",
            )

    async def token(self, owner, request_id, deadline, *, invalid_token=None, locked=False):
        row = await self.repository.current(owner)
        if row["status"] != "active":
            raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "请修复学校认证后重试")
        credential = UUID(bytes=row["id"])
        key = f"school_adapter:token:{credential}:{row['version']}"
        cached = await self.store.get_secret(key)
        if cached and cached["token"] != invalid_token:
            return cached["token"], self.repository.payload(row)["school_user_id"], row
        payload = self.repository.payload(row)
        alias = lookup_aliases(self.lookup, "hbue", payload["student_id"])[self.lookup.current]
        context = nullcontext() if locked else self.store.account_lock(alias, deadline=deadline)
        async with context:
            latest = await self.repository.current(owner)
            if latest["version"] != row["version"] or latest["status"] != "active":
                raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化，请重试")
            cached = await self.store.get_secret(key)
            if cached and cached["token"] != invalid_token:
                return cached["token"], payload["school_user_id"], row
            try:
                if not row["use_allowed"]:
                    raise ApiError(
                        409,
                        ErrorCode.SCHOOL_REAUTH_REQUIRED,
                        "当前学校会话已过期，请手动认证；后台凭据使用未授权",
                    )
                await self.store.rate("background_login", alias, limit=2, window=300)
                token, school_user = await self.background_auth(payload, deadline)
            except ApiError as error:
                if error.code in {
                    ErrorCode.SCHOOL_LOGIN_REJECTED,
                    ErrorCode.SCHOOL_REAUTH_REQUIRED,
                }:
                    await self.repository.require_reauth(row, request_id)
                    await self.store.call("delete", key)
                    raise ApiError(
                        409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校认证需要人工修复，请重新登录"
                    ) from None
                raise
            latest = await self.repository.current(owner)
            if latest["version"] != row["version"] or latest["status"] != "active":
                raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化，请重试")
            if school_user != payload["school_user_id"]:
                raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校用户标识发生变化")
            await cache_token(
                self.repository, self.store, owner, credential, row["version"], {"token": token}
            )
            return token, school_user, row

    async def read(self, owner, request_id, path, params, *, include_user=False):
        deadline = Deadline(25)
        try:
            async with asyncio.timeout(deadline.remaining()):
                row = await self.repository.current(owner)
                if row["status"] != "active":
                    raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "请修复学校认证后重试")
                payload = self.repository.payload(row)
                alias = lookup_aliases(self.lookup, "hbue", payload["student_id"])[
                    self.lookup.current
                ]
                async with self.store.account_lock(alias, deadline=deadline):
                    token, school_user, row = await self.token(
                        owner, request_id, deadline, locked=True
                    )
                    query = {**params, **({"userId": school_user} if include_user else {})}
                    value, row = await self.read_attempts(
                        owner, request_id, path, query, token, row, deadline
                    )
                    latest = await self.repository.current(owner)
                    if latest["version"] != row["version"] or latest["status"] != "active":
                        raise ApiError(
                            409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化，请刷新后重试"
                        )
                    return value
        except TimeoutError:
            raise ApiError(
                504, ErrorCode.SCHOOL_TIMEOUT, "学校查询超时，请稍后重试", True
            ) from None

    async def read_attempts(self, owner, request_id, path, query, token, row, deadline):
        for attempt in range(2):
            try:
                return await self.protocol.read(path, token, query, deadline=deadline), row
            except ApiError as error:
                if error.code == ErrorCode.SCHOOL_REAUTH_REQUIRED:
                    if attempt == 1:
                        await self.repository.require_reauth(row, request_id)
                        key = f"school_adapter:token:{UUID(bytes=row['id'])}:{row['version']}"
                        await self.store.call("delete", key)
                        raise
                    token, school_user, row = await self.token(
                        owner, request_id, deadline, invalid_token=token, locked=True
                    )
                elif attempt == 0 and error.code in {
                    ErrorCode.SCHOOL_UNAVAILABLE,
                    ErrorCode.SCHOOL_TIMEOUT,
                }:
                    await asyncio.sleep(min(random.uniform(0.05, 0.2), deadline.remaining()))
                else:
                    raise
