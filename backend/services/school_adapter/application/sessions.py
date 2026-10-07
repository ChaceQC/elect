import asyncio
import random
from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.crypto import lookup_aliases
from ..infrastructure.ocr import solve_image
from ..infrastructure.ocr_executor import OcrExecutor
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
        self.ocr_executor = OcrExecutor(solver)

    async def background_auth(self, payload, deadline):
        from .background_auth import authenticate

        return await authenticate(self.protocol, self.ocr_executor, payload, deadline)

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

    async def read(
        self, owner, request_id, path, params, *, include_user=False, budget=25, read_timeout=12,
        observer=None,
    ):
        deadline = Deadline(budget)
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
                    try:
                        value, row = await self.read_attempts(
                            owner, request_id, path, query, token, row, deadline, read_timeout
                        )
                    except ApiError as error:
                        if observer:
                            return await observer(None, error.code, datetime.now(UTC))
                        raise
                    observed_at = datetime.now(UTC)
                    latest = await self.repository.current(owner)
                    if latest["version"] != row["version"] or latest["status"] != "active":
                        raise ApiError(
                            409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化，请刷新后重试"
                        )
                    return await observer(value, None, observed_at) if observer else value
        except TimeoutError:
            raise ApiError(
                504, ErrorCode.SCHOOL_TIMEOUT, "学校查询超时，请稍后重试", True
            ) from None

    async def read_bound(self, owner, request_id, *, budget=25, read_timeout=12):
        from functools import partial

        from ..infrastructure.balance_observations import observe

        return await self.read(
            owner, request_id, "/base/roomUser/selectRoomListByUserId", {}, include_user=True,
            budget=budget, read_timeout=read_timeout,
            observer=partial(observe, self.repository.engine, owner, request_id),
        )

    async def read_attempts(
        self, owner, request_id, path, query, token, row, deadline, read_timeout
    ):
        for attempt in range(2):
            try:
                return await self.protocol.read(
                    path, token, query, deadline=deadline, read_timeout=read_timeout
                ), row
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

    async def bind_once(self, command, record, reserve):
        async def send(token, school_user, deadline):
            return await self.protocol.bind_one(token, {**record, "userId": school_user}, deadline)

        return await self.write_once(command, reserve, send)

    async def remove_once(self, command, relation_id, reserve):
        async def send(token, school_user, deadline):
            return await self.protocol.remove_one(token, relation_id, deadline)

        return await self.write_once(command, reserve, send)

    async def write_once(self, command, reserve, send):
        deadline = Deadline(60)
        try:
            async with asyncio.timeout(deadline.remaining()):
                row = await self.repository.current(command.owner_user_id)
                if row["status"] != "active" or not row["use_allowed"]:
                    raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "请修复学校认证后绑定")
                payload = self.repository.payload(row)
                alias = lookup_aliases(self.lookup, "hbue", payload["student_id"])[
                    self.lookup.current
                ]
                async with self.store.account_lock(alias, deadline=deadline):
                    token, school_user, row = await self.token(
                        command.owner_user_id, command.request_id, deadline, locked=True
                    )
                    if (
                        row["id"] != command.credential_ref.bytes
                        or row["version"] != command.credential_version
                    ):
                        raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化")
                    if not await reserve():
                        return None
                    return await send(token, school_user, deadline)
        except TimeoutError:
            raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "学校绑定结果待确认", True) from None
