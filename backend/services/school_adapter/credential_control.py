"""凭据控制的内部证明和撤销；密码/学校用户密文删除，账号展示单独加密。"""

from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first


def display_aad(owner, credential):
    return f"hbue:display:{owner}:{credential}"


async def proof(repository, owner):
    try:
        row = await repository.current(owner)
    except ApiError as error:
        if error.code != ErrorCode.SCHOOL_REAUTH_REQUIRED:
            raise
        return {
            "credential_ref": None,
            "credential_version": 0,
            "state": "missing",
            "use_allowed": False,
        }
    return {
        "credential_ref": str(UUID(bytes=row["id"])),
        "credential_version": row["version"],
        "state": row["status"],
        "use_allowed": bool(row["use_allowed"]),
    }


async def require_barrier(app, principal, operation, credential, version, kind):
    value = await app.state.service_client.call(
        "monitoring",
        "/credentials/barrier",
        "monitor:credential-read",
        principal.request_id,
        {"operation_id": str(operation)},
        principal=principal,
    )
    if (
        value["credential_ref"] != str(credential)
        or value["expected_credential_version"] != version
        or value["kind"] != kind
        or value["state"] not in {"prepared", "committed"}
    ):
        raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "凭据控制屏障尚未确认")


async def revoke(repository, store, command):
    async with repository.engine.begin() as conn:
        row = await first(
            conn,
            "SELECT * FROM school_credentials WHERE id=:id FOR UPDATE",
            id=command.credential_ref.bytes,
        )
        existing = await first(
            conn, "SELECT * FROM credential_revocations WHERE id=:id", id=command.operation_id.bytes
        )
        if existing:
            if (
                existing["owner_user_id"] != command.owner_user_id.bytes
                or existing["credential_ref"] != command.credential_ref.bytes
                or existing["credential_version"] != command.expected_credential_version
            ):
                raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "撤回操作编号已被使用")
        else:
            if not row or row["owner_user_id"] != command.owner_user_id.bytes:
                raise ApiError(404, ErrorCode.NOT_FOUND, "凭据不存在")
            if row["version"] != command.expected_credential_version:
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "凭据版本已变化")
            display = row["account_display"]
            if display is None:
                display = repository.crypto.seal(
                    repository.payload(row)["student_id"],
                    display_aad(command.owner_user_id, command.credential_ref),
                )
            await execute(
                conn,
                "UPDATE school_credentials SET account_display=:display,status='revoked',"
                "use_allowed=0,ciphertext='',wrapped_dek='',school_user_id_ciphertext='',"
                "revoked_at=UTC_TIMESTAMP(6),updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=command.credential_ref.bytes,
                display=display,
            )
            await execute(
                conn,
                "UPDATE credential_staging SET state='expired',encrypted_payload='',wrapped_dek='' "
                "WHERE credential_ref=:id AND state IN ('staged','activated')",
                id=command.credential_ref.bytes,
            )
            await execute(
                conn,
                "INSERT INTO credential_revocations "
                "(id,owner_user_id,credential_ref,credential_version) "
                "VALUES (:id,:owner,:ref,:version)",
                id=command.operation_id.bytes,
                owner=command.owner_user_id.bytes,
                ref=command.credential_ref.bytes,
                version=command.expected_credential_version,
            )
            await repository.activation_events(
                conn,
                command,
                command.expected_credential_version,
                event_type="credential.revoked",
                action="credential.revoked",
            )
    # 持久 revoked 已阻断使用；Redis 不可用时由同一持久操作重试清理，不伪报完成。
    from .application.token_cache import clear_revoked_tokens

    await clear_revoked_tokens(
        repository, store, command.credential_ref, command.expected_credential_version
    )
    return {
        "credential_ref": str(command.credential_ref),
        "credential_version": command.expected_credential_version,
        "state": "revoked",
    }
