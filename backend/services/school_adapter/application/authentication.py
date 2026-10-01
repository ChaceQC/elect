import asyncio
from datetime import UTC, datetime

from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.crypto import lookup_aliases
from ..infrastructure.transport import Deadline


class Authentication:
    def __init__(self, repository, store, protocol, lookup):
        self.repository, self.store, self.protocol, self.lookup = (
            repository,
            store,
            protocol,
            lookup,
        )

    async def authenticate(self, command):
        deadline = Deadline(60)
        try:
            async with asyncio.timeout(deadline.remaining()):
                return await self._authenticate(command, deadline)
        except TimeoutError:
            raise ApiError(
                504, ErrorCode.SCHOOL_TIMEOUT, "学校登录超时，请查询当前结果或重新取图", True
            ) from None

    async def _authenticate(self, command, deadline):
        staged = await self.repository.staged(command.attempt_id)
        if staged:
            return self.repository.stage_result(staged)
        aliases = lookup_aliases(self.lookup, "hbue", command.student_id)
        alias = aliases[self.lookup.current]
        await self.store.rate("login", alias)
        await self.store.rate("browser_login", command.browser_nonce_hash)
        async with self.store.account_lock(alias, deadline=deadline):
            staged = await self.repository.staged(command.attempt_id)
            if staged:
                return self.repository.stage_result(staged)
            challenge = await self.store.consume_challenge(
                command.browser_nonce_hash, command.challenge_id
            )
            token, school_user_id = await self.protocol.authenticate(
                command.student_id,
                command.password.get_secret_value(),
                challenge,
                command.captcha_answer,
                deadline=deadline,
            )
            result = await self.repository.stage(
                command.attempt_id,
                command.student_id,
                command.password.get_secret_value(),
                school_user_id,
                aliases,
            )
            await self.store.put_secret(
                f"school_adapter:staged_token:{command.attempt_id}", {"token": token}, ttl=600
            )
            return result

    async def activate(self, command):
        version = await self.repository.activate(command)
        staged = await self.store.get_secret(f"school_adapter:staged_token:{command.attempt_id}")
        row = await self.repository.current(command.owner_user_id)
        if row["version"] != version:
            raise ApiError(409, ErrorCode.VERSION_CONFLICT, "登录凭据已被更新，请重新认证")
        if staged:
            await self.store.put_secret(
                f"school_adapter:token:{command.credential_ref}:{version}", staged
            )
        return {
            "credential_ref": str(command.credential_ref),
            "credential_version": version,
            "state": "active",
        }

    async def stage_status(self, attempt_id):
        staged = await self.repository.staged(attempt_id)
        if not staged or (
            staged["state"] != "activated"
            and staged["expires_at"].replace(tzinfo=UTC) <= datetime.now(UTC)
        ):
            raise ApiError(404, ErrorCode.NOT_FOUND, "登录暂存不存在")
        return self.repository.stage_result(staged)
