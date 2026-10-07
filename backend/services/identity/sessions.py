import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import aware, execute, first


class AppSessions:
    def __init__(self, engine, pepper):
        self.engine, self.pepper = engine, pepper

    def digest(self, value, *, purpose="session"):
        return hmac.new(self.pepper, (purpose + ":" + value).encode(), hashlib.sha256).digest()

    def csrf(self, token):
        return base64.urlsafe_b64encode(self.digest(token, purpose="csrf")).decode().rstrip("=")

    async def context(self, token, *, required=True):
        if not isinstance(token, str) or len(token) != 43:
            return self.expired(required)
        async with self.engine.begin() as conn:
            row = await self.read(conn, token)
            if not self.valid(row):
                return self.expired(required)
            csrf = self.csrf(token)
            if not hmac.compare_digest(hashlib.sha256(csrf.encode()).digest(), row["csrf_hash"]):
                return self.expired(required)
            if row["last_seen_at"] <= row["checked_at"] - timedelta(seconds=60):
                await execute(
                    conn,
                    "UPDATE app_sessions s JOIN users u ON u.id=s.user_id "
                    "SET s.last_seen_at=UTC_TIMESTAMP(6),s.expires_at="
                    "LEAST(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 12 HOUR),s.absolute_expires_at),"
                    "s.updated_at=UTC_TIMESTAMP(6) WHERE s.id=:id AND s.revoked_at IS NULL "
                    "AND u.status='active' AND s.session_version=u.session_version "
                    "AND s.expires_at>UTC_TIMESTAMP(6) AND s.absolute_expires_at>UTC_TIMESTAMP(6) "
                    "AND s.last_seen_at<=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 60 SECOND)",
                    id=row["id"],
                )
                # 条件失败可能是并发续期，也可能已撤销/禁用/过期；只返回权威结果。
                row = await self.read(conn, token)
                if not self.valid(row):
                    return self.expired(required)
            return {**row, "expires_at": aware(row["expires_at"]), "csrf_token": csrf}

    async def read(self, conn, token):
        return await first(
            conn,
            "SELECT s.*,u.credential_ref,u.status AS user_status,"
            "u.session_version AS user_version,UTC_TIMESTAMP(6) AS checked_at "
            "FROM app_sessions s JOIN users u ON s.user_id=u.id WHERE s.token_hash=:hash",
            hash=self.digest(token),
        )

    @staticmethod
    def valid(row):
        return bool(row and not row["revoked_at"] and row["user_status"] == "active"
                    and row["session_version"] == row["user_version"]
                    and row["expires_at"] > row["checked_at"]
                    and row["absolute_expires_at"] > row["checked_at"])

    @staticmethod
    def expired(required):
        if required:
            raise ApiError(401, ErrorCode.APP_SESSION_EXPIRED, "应用会话已过期，请重新登录")
        return None

    async def issue(self, attempt, request_id):
        token, csrf = secrets.token_urlsafe(32), None
        csrf = self.csrf(token)
        now, session_id = datetime.now(UTC).replace(tzinfo=None), new_id()
        async with self.engine.begin() as conn:
            row = await first(
                conn, "SELECT * FROM login_attempts WHERE id=:id FOR UPDATE", id=attempt["id"]
            )
            if row["state"] not in {"activated", "session_issued"}:
                raise RuntimeError("凭据未确认激活，禁止签发会话")
            user = await first(
                conn, "SELECT * FROM users WHERE id=:id FOR UPDATE", id=row["user_id"]
            )
            if user["status"] != "active":
                raise ApiError(401, ErrorCode.APP_SESSION_EXPIRED, "应用账户不可用")
            if (
                user["credential_operation_id"] is not None
                or user["credential_status"] not in {"active", "requires_reauth"}
                or user["credential_version"] != row["credential_version"]
            ):
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "凭据授权已变化，请重新认证")
            if row["issued_session_id"]:
                await execute(
                    conn,
                    "UPDATE app_sessions SET revoked_at=UTC_TIMESTAMP(6),"
                    "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                    id=row["issued_session_id"],
                )
            if row["state"] == "activated":
                await execute(
                    conn,
                    "INSERT INTO consents (id,user_id,agreement_version,content_hash,"
                    "accepted_at,credential_use_allowed) VALUES "
                    "(:id,:user,:version,:hash,:now,:allowed)",
                    id=new_id().bytes,
                    user=row["user_id"],
                    version=row["agreement_version"],
                    hash=row["content_hash"],
                    now=now,
                    allowed=row["credential_use_allowed"],
                )
            await execute(
                conn,
                "INSERT INTO app_sessions (id,user_id,token_hash,csrf_hash,expires_at,"
                "absolute_expires_at,last_seen_at,session_version) VALUES "
                "(:id,:user,:hash,:csrf,:expires,:absolute,:now,:version)",
                id=session_id.bytes,
                user=row["user_id"],
                hash=self.digest(token),
                csrf=hashlib.sha256(csrf.encode()).digest(),
                expires=now + timedelta(hours=12),
                absolute=now + timedelta(days=7),
                now=now,
                version=user["session_version"],
            )
            await execute(
                conn,
                "UPDATE login_attempts SET state='session_issued',issued_session_id=:sid,"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                sid=session_id.bytes,
                id=row["id"],
            )
            await record_audit(
                conn,
                "identity",
                "session.issued",
                "session",
                session_id,
                request_id,
                actor=UUID(bytes=row["user_id"]),
            )
        return token

    async def logout(self, row, request_id):
        async with self.engine.begin() as conn:
            result = await execute(
                conn,
                "UPDATE app_sessions SET revoked_at=UTC_TIMESTAMP(6),"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id AND revoked_at IS NULL",
                id=row["id"],
            )
            if result.rowcount:
                await record_audit(
                    conn,
                    "identity",
                    "session.logged_out",
                    "session",
                    UUID(bytes=row["id"]),
                    request_id,
                    actor=UUID(bytes=row["user_id"]),
                )
