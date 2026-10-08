"""按 challenge/匿名 nonce 恢复的持久 Saga；任何失败不先发会话。"""

import hashlib
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import StagedCredential
from services.common.sql import aware, execute, first

from ..agreement import agreement
from .login_gate import LoginGate, busy


class LoginSaga:
    def __init__(self, engine, client, sessions):
        self.engine, self.client, self.sessions = engine, client, sessions
        self.gate = LoginGate()

    async def attempt(self, login, nonce_hash, current_user):
        digest = self.sessions.digest(login.model_dump_json() + nonce_hash, purpose="login")
        challenge = hashlib.sha256((nonce_hash + ":" + login.challenge_id).encode()).digest()
        policy = agreement()
        if login.agreement_version != policy.version:
            raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "协议版本已更新，请重新阅读并同意")
        student = login.student_id
        if student != student.strip() or any(c.isspace() or not c.isprintable() for c in student):
            raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "学校账号不能包含空白或控制字符")
        # SecretStr 的默认 JSON 脱敏不能作为请求摘要，显式加入仅内存中的密码 HMAC。
        digest = hmac.new(
            digest, login.password.get_secret_value().encode(), hashlib.sha256
        ).digest()
        try:
            async with self.engine.begin() as conn:
                await execute(
                    conn,
                    "INSERT INTO login_attempts (id,browser_nonce_hash,challenge_hash,"
                    "request_digest,expected_user_id,state,expires_at,agreement_version,"
                    "content_hash,credential_use_allowed,next_reconcile_at) VALUES "
                    "(:id,:nonce,:challenge,:digest,:expected,'created',:expires,:agreement,"
                    ":content,:allowed,UTC_TIMESTAMP(6))",
                    id=new_id().bytes,
                    nonce=bytes.fromhex(nonce_hash),
                    challenge=challenge,
                    digest=digest,
                    expected=current_user.bytes if current_user else None,
                    expires=(datetime.now(UTC) + timedelta(minutes=10)).replace(tzinfo=None),
                    agreement=policy.version,
                    content=bytes.fromhex(policy.content_hash),
                    allowed=login.credential_use_allowed,
                )
        except IntegrityError:
            pass
        async with self.engine.connect() as conn:
            row = await first(
                conn, "SELECT * FROM login_attempts WHERE challenge_hash=:hash", hash=challenge
            )
        if (
            not row
            or row["browser_nonce_hash"] != bytes.fromhex(nonce_hash)
            or not hmac.compare_digest(row["request_digest"], digest)
            or row["expected_user_id"] != (current_user.bytes if current_user else None)
        ):
            raise ApiError(400, ErrorCode.CAPTCHA_INVALID, "验证码提交不匹配，请重新取图")
        if aware(row["expires_at"]) <= datetime.now(UTC) or row["state"] in {"expired", "failed"}:
            raise ApiError(400, ErrorCode.CAPTCHA_EXPIRED, "登录尝试已结束，请重新取图")
        return row

    async def state(self, attempt_id, state, **values):
        # 重试写入中间阶段不代表恢复成功；错误保留到终态后退出恢复健康统计。
        async with self.engine.begin() as conn:
            await execute(
                conn,
                "UPDATE login_attempts SET state=:state,error_code=COALESCE(:error,error_code),"
                "next_reconcile_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 5 SECOND),"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id AND state NOT IN "
                "('session_issued','failed','expired')",
                id=attempt_id.bytes,
                state=state,
                error=values.get("error"),
            )

    async def read(self, attempt_id):
        async with self.engine.connect() as conn:
            return await first(
                conn, "SELECT * FROM login_attempts WHERE id=:id", id=attempt_id.bytes
            )

    async def reject_uncommitted(self, attempt_id, error):
        # 恢复器释放锁后前台可能已提交身份；拒绝不能覆盖已提交或终结的尝试。
        async with self.engine.begin() as conn:
            result = await execute(
                conn,
                "UPDATE login_attempts SET state='failed',error_code=:error,"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id "
                "AND state IN ('created','authenticating','staged')",
                id=attempt_id.bytes, error=error,
            )
        return result.rowcount > 0

    @asynccontextmanager
    async def locked(self, attempt_id, *, background=False):
        async with self.gate.enter(background=background), self.engine.connect() as conn:
            name = f"identity:login:{attempt_id}"
            try:
                acquired = await first(conn, "SELECT GET_LOCK(:name,0) AS acquired", name=name)
            except BaseException:
                # 获取结果丢失时也不能将可能持锁的连接放回池。
                await conn.invalidate()
                raise
            if not acquired["acquired"]:
                raise busy()
            try:
                yield
            finally:
                try:
                    released = await first(
                        conn, "SELECT RELEASE_LOCK(:name) AS released", name=name,
                    )
                    if released["released"] != 1:
                        await conn.invalidate()
                except BaseException:
                    await conn.invalidate()
                    raise

    async def identity_commit(self, row, staged):
        async with self.engine.begin() as conn:
            locked = await first(
                conn, "SELECT * FROM login_attempts WHERE id=:id FOR UPDATE", id=row["id"]
            )
            if locked["user_id"] is not None:
                return
            user = await first(
                conn,
                "SELECT * FROM users WHERE credential_ref=:ref FOR UPDATE",
                ref=staged.credential_ref.bytes,
            )
            if row["expected_user_id"] and (not user or user["id"] != row["expected_user_id"]):
                raise ApiError(
                    409,
                    ErrorCode.REAUTH_ACCOUNT_MISMATCH,
                    "请使用当前应用账户对应的学校账号重新认证",
                )
            if not user:
                user_id = new_id()
                await execute(
                    conn,
                    "INSERT INTO users (id,school_id,credential_ref,status,"
                    "session_version) VALUES (:id,'hbue',:ref,'active',1)",
                    id=user_id.bytes,
                    ref=staged.credential_ref.bytes,
                )
            else:
                if user["status"] != "active":
                    raise ApiError(401, ErrorCode.APP_SESSION_EXPIRED, "应用账户不可用")
                if user["credential_operation_id"] not in {None, row["id"]}:
                    raise ApiError(
                        503, ErrorCode.DEPENDENCY_UNAVAILABLE, "凭据操作正在完成，请稍后重试", True
                    )
                user_id = UUID(bytes=user["id"])
            await execute(
                conn,
                "UPDATE users SET credential_operation_id=:operation WHERE id=:id",
                operation=row["id"],
                id=user_id.bytes,
            )
            await execute(
                conn,
                "UPDATE login_attempts SET state='identity_committed',user_id=:user,"
                "credential_ref=:ref,credential_version=:version,"
                "expected_credential_version=:expected,updated_at=UTC_TIMESTAMP(6) "
                "WHERE id=:id",
                user=user_id.bytes,
                ref=staged.credential_ref.bytes,
                version=staged.credential_version,
                expected=staged.credential_version - 1 or None,
                id=row["id"],
            )

    async def advance(self, row, request_id, *, login=None, nonce_hash=None):
        attempt_id = UUID(bytes=row["id"])
        if row["state"] in {"created", "authenticating", "staged"}:
            if login:
                await self.state(attempt_id, "authenticating")
                staged = await self.client.call(
                    "school_adapter",
                    "/login-attempts/authenticate",
                    "credential:authenticate",
                    request_id,
                    {
                        "attempt_id": str(attempt_id),
                        "browser_nonce_hash": nonce_hash,
                        "challenge_id": login.challenge_id,
                        "student_id": login.student_id,
                        "password": login.password.get_secret_value(),
                        "captcha_answer": login.captcha_answer,
                        "request_id": str(request_id),
                    },
                )
            else:
                staged = await self.client.call(
                    "school_adapter",
                    "/login-attempts/status",
                    "credential:authenticate",
                    request_id,
                    {"attempt_id": str(attempt_id)},
                )
            await self.state(attempt_id, "staged")
            await self.identity_commit(row, StagedCredential.model_validate(staged))
            row = await self.read(attempt_id)
        if row["state"] in {"identity_committed", "activating"}:
            await self.state(attempt_id, "activating")
            from .credential_activation import CredentialActivation

            await CredentialActivation(self.engine, self.client).activate(row, request_id)
            row = await self.read(attempt_id)
        return row

    async def login(self, login, nonce_hash, current_user, request_id):
        row = await self.attempt(login, nonce_hash, current_user)
        attempt_id = UUID(bytes=row["id"])
        async with self.locked(attempt_id):
            row = await self.read(attempt_id)
            try:
                row = await self.advance(row, request_id, login=login, nonce_hash=nonce_hash)
            except ApiError as error:
                if error.status < 500:
                    # 认证限流也是明确拒绝；没有已验证暂存时后台不能重提密码。
                    await self.reject_uncommitted(attempt_id, error.code)
                raise
            return await self.sessions.issue(row, request_id)
