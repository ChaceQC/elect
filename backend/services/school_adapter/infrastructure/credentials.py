"""只访问 elect_school 的暂存与版本激活，不接收未验证密码写入。"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.events import CredentialPayload
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope, StagedCredential
from services.common.outbox import append_event
from services.common.sql import aware, execute, first

from .crypto import credential_aad


class CredentialRepository:
    def __init__(self, engine, crypto):
        self.engine, self.crypto = engine, crypto

    async def staged(self, attempt_id):
        async with self.engine.connect() as conn:
            return await first(
                conn, "SELECT * FROM credential_staging WHERE attempt_id=:id", id=attempt_id.bytes
            )

    def stage_result(self, row):
        if row["state"] not in {"staged", "activated"} or not row["encrypted_payload"]:
            raise ApiError(400, ErrorCode.CAPTCHA_EXPIRED, "登录暂存已失效，请重新认证")
        aad = credential_aad(
            UUID(bytes=row["credential_ref"]),
            UUID(bytes=row["attempt_id"]),
            row["candidate_version"],
        )
        envelope = {**row, "ciphertext": row["encrypted_payload"]}
        value = self.crypto.decrypt(envelope, aad)
        return StagedCredential(
            attempt_id=UUID(bytes=row["attempt_id"]),
            credential_ref=UUID(bytes=row["credential_ref"]),
            credential_version=row["candidate_version"],
            lookup_aliases=value["aliases"],
            expires_at=aware(row["expires_at"]),
        )

    async def observe(self, aliases):
        async with self.engine.connect() as conn:
            for version, digest in aliases.items():
                row = await first(
                    conn,
                    "SELECT c.id,c.version,c.revoked_at FROM school_credentials c "
                    "JOIN account_lookup a ON a.credential_id=c.id "
                    "WHERE a.school_id='hbue' AND a.key_version=:version AND a.lookup_hash=:hash",
                    version=version,
                    hash=bytes.fromhex(digest),
                )
                if row:
                    return dict(row)
        return None

    async def stage(self, attempt_id, student_id, password, school_user_id, aliases, *, observed):
        async with self.engine.begin() as conn:
            existing = await first(
                conn,
                "SELECT * FROM credential_staging WHERE attempt_id=:id FOR UPDATE",
                id=attempt_id.bytes,
            )
            if existing:
                return self.stage_result(existing)
            refs = set()
            for version, digest in aliases.items():
                row = await first(
                    conn,
                    "SELECT credential_id FROM account_reservations "
                    "WHERE school_id='hbue' AND key_version=:version "
                    "AND lookup_hash=:hash FOR UPDATE",
                    version=version,
                    hash=bytes.fromhex(digest),
                )
                lookup = await first(
                    conn,
                    "SELECT credential_id FROM account_lookup "
                    "WHERE school_id='hbue' AND key_version=:version "
                    "AND lookup_hash=:hash",
                    version=version,
                    hash=bytes.fromhex(digest),
                )
                for match in (row, lookup):
                    if match:
                        refs.add(match["credential_id"])
            if len(refs) > 1:
                raise RuntimeError("账号密钥别名存在冲突")
            credential = UUID(bytes=refs.pop()) if refs else new_id()
            for version, digest in aliases.items():
                await execute(
                    conn,
                    "INSERT INTO account_reservations "
                    "(school_id,key_version,lookup_hash,credential_id) "
                    "VALUES ('hbue',:version,:hash,:id) "
                    "ON DUPLICATE KEY UPDATE credential_id=credential_id",
                    version=version,
                    hash=bytes.fromhex(digest),
                    id=credential.bytes,
                )
                reserved = await first(
                    conn,
                    "SELECT credential_id FROM account_reservations "
                    "WHERE school_id='hbue' AND key_version=:version "
                    "AND lookup_hash=:hash",
                    version=version,
                    hash=bytes.fromhex(digest),
                )
                if reserved["credential_id"] != credential.bytes:
                    raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "账号正在建立，请稍后重试")
            current = await first(
                conn,
                "SELECT id,version,revoked_at FROM school_credentials WHERE id=:id FOR UPDATE",
                id=credential.bytes,
            )
            if (dict(current) if current else None) != observed:
                raise ApiError(
                    409, ErrorCode.VERSION_CONFLICT, "认证期间学校授权已变化，请重新认证"
                )
            version = current["version"] + 1 if current else 1
            payload = {
                "student_id": student_id,
                "password": password,
                "school_user_id": school_user_id,
                "aliases": aliases,
            }
            encrypted = self.crypto.encrypt(
                payload, credential_aad(credential, attempt_id, version)
            )
            expires = datetime.now(UTC) + timedelta(minutes=10)
            await execute(
                conn,
                "INSERT INTO credential_staging (attempt_id,credential_ref,"
                "encrypted_payload,wrapped_dek,nonce,kek_version,algorithm,"
                "candidate_version,expires_at,state) VALUES (:attempt,:credential,"
                ":ciphertext,:wrapped_dek,:nonce,:kek_version,:algorithm,:version,"
                ":expires,'staged')",
                attempt=attempt_id.bytes,
                credential=credential.bytes,
                version=version,
                expires=expires.replace(tzinfo=None),
                **encrypted,
            )
            return StagedCredential(
                attempt_id=attempt_id,
                credential_ref=credential,
                credential_version=version,
                lookup_aliases=aliases,
                expires_at=expires,
            )

    async def activate(self, command):
        async with self.engine.begin() as conn:
            current = await first(
                conn,
                "SELECT * FROM school_credentials WHERE id=:id FOR UPDATE",
                id=command.credential_ref.bytes,
            )
            staged = await first(
                conn,
                "SELECT * FROM credential_staging WHERE attempt_id=:id FOR UPDATE",
                id=command.attempt_id.bytes,
            )
            if not staged or staged["credential_ref"] != command.credential_ref.bytes:
                raise ApiError(404, ErrorCode.NOT_FOUND, "登录暂存不存在")
            if staged["state"] == "activated":
                if staged["owner_user_id"] != command.owner_user_id.bytes:
                    raise ApiError(404, ErrorCode.NOT_FOUND, "登录暂存不存在")
                return staged["candidate_version"]
            if staged["state"] != "staged" or aware(staged["expires_at"]) <= datetime.now(UTC):
                raise ApiError(400, ErrorCode.CAPTCHA_EXPIRED, "登录暂存已过期，请重新认证")
            if current and current["owner_user_id"] != command.owner_user_id.bytes:
                raise ApiError(404, ErrorCode.NOT_FOUND, "凭据不存在")
            version = staged["candidate_version"]
            if (
                current["version"] if current else None
            ) != command.expected_credential_version or version != (
                current["version"] + 1 if current else 1
            ):
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "凭据已更新，请重新认证")
            payload = self.crypto.decrypt(
                {**staged, "ciphertext": staged["encrypted_payload"]},
                credential_aad(command.credential_ref, command.attempt_id, version),
            )
            aad = credential_aad(command.credential_ref, command.owner_user_id, version)
            encrypted = self.crypto.encrypt(payload, aad)
            school_user = self.crypto.seal(payload["school_user_id"], aad + ":school_user")
            params = dict(
                id=command.credential_ref.bytes,
                owner=command.owner_user_id.bytes,
                version=version,
                school_user=school_user,
                allowed=command.credential_use_allowed,
                **encrypted,
            )
            if current:
                await execute(
                    conn,
                    "UPDATE school_credentials SET ciphertext=:ciphertext,"
                    "nonce=:nonce,wrapped_dek=:wrapped_dek,kek_version=:kek_version,"
                    "school_user_id_ciphertext=:school_user,algorithm=:algorithm,"
                    "version=:version,status='active',use_allowed=:allowed,"
                    "verified_at=UTC_TIMESTAMP(6),revoked_at=NULL,"
                    "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                    **params,
                )
            else:
                await execute(
                    conn,
                    "INSERT INTO school_credentials (id,owner_user_id,school_id,"
                    "school_user_id_ciphertext,ciphertext,nonce,wrapped_dek,kek_version,"
                    "algorithm,version,status,use_allowed,verified_at) VALUES "
                    "(:id,:owner,'hbue',:school_user,:ciphertext,:nonce,:wrapped_dek,"
                    ":kek_version,:algorithm,:version,'active',:allowed,UTC_TIMESTAMP(6))",
                    **params,
                )
            for key, digest in payload["aliases"].items():
                await execute(
                    conn,
                    "INSERT INTO account_lookup "
                    "(school_id,key_version,lookup_hash,credential_id) "
                    "VALUES ('hbue',:key,:hash,:id) "
                    "ON DUPLICATE KEY UPDATE credential_id=credential_id",
                    key=key,
                    hash=bytes.fromhex(digest),
                    id=command.credential_ref.bytes,
                )
            await execute(
                conn,
                "UPDATE credential_staging SET state='activated',owner_user_id=:owner,"
                "updated_at=UTC_TIMESTAMP(6) WHERE attempt_id=:id",
                owner=command.owner_user_id.bytes,
                id=command.attempt_id.bytes,
            )
            await self.activation_events(conn, command, version)
            return version

    async def activation_events(
        self,
        conn,
        command,
        version,
        *,
        event_type="credential.updated",
        action="credential.activated",
    ):
        await append_event(
            conn,
            EventEnvelope(
                event_id=new_id(),
                type=event_type,
                schema_version=1,
                producer="school_adapter",
                aggregate_id=command.credential_ref,
                aggregate_version=version,
                occurred_at=datetime.now(UTC),
                request_id=command.request_id,
                dedupe_key=f"credential:{command.credential_ref}:{version}:{event_type}",
                payload=CredentialPayload(
                    credential_id=command.credential_ref,
                    owner_user_id=command.owner_user_id,
                    credential_version=version,
                ),
            ),
        )
        await record_audit(
            conn,
            "school_adapter",
            action,
            "credential",
            command.credential_ref,
            command.request_id,
            actor=command.owner_user_id,
            version=version,
        )

    async def current(self, owner):
        async with self.engine.connect() as conn:
            row = await first(
                conn,
                "SELECT * FROM school_credentials WHERE owner_user_id=:owner AND school_id='hbue'",
                owner=owner.bytes,
            )
        if not row:
            raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "请重新进行学校认证")
        return row

    def payload(self, row):
        return self.crypto.decrypt(
            row,
            credential_aad(UUID(bytes=row["id"]), UUID(bytes=row["owner_user_id"]), row["version"]),
        )

    async def require_reauth(self, row, request_id):
        async with self.engine.begin() as conn:
            result = await execute(
                conn,
                "UPDATE school_credentials SET status='requires_reauth',"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id AND version=:version "
                "AND status='active'",
                id=row["id"],
                version=row["version"],
            )
            if result.rowcount:
                await append_event(
                    conn,
                    EventEnvelope(
                        event_id=new_id(),
                        type="credential.requires_reauth",
                        schema_version=1,
                        producer="school_adapter",
                        aggregate_id=UUID(bytes=row["id"]),
                        aggregate_version=row["version"],
                        occurred_at=datetime.now(UTC),
                        request_id=request_id,
                        dedupe_key=f"credential:{UUID(bytes=row['id'])}:reauth:{row['version']}",
                        payload=CredentialPayload(
                            credential_id=UUID(bytes=row["id"]),
                            owner_user_id=UUID(bytes=row["owner_user_id"]),
                            credential_version=row["version"],
                        ),
                    ),
                )
                await record_audit(
                    conn,
                    "school_adapter",
                    "credential.requires_reauth",
                    "credential",
                    UUID(bytes=row["id"]),
                    request_id,
                    actor=UUID(bytes=row["owner_user_id"]),
                    result="failed",
                    version=row["version"],
                )
