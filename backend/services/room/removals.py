"""学校解绑的本域受理/提交；只在缺席确认后标 inactive，保留缓存与历史。"""

import hashlib
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import CredentialProof
from services.common.sql import execute, first

from .preference_store import lock_preference, locked_operation


async def replay(conn, owner, binding, key):
    row = await first(
        conn,
        "SELECT * FROM room_operations WHERE owner_user_id=:owner "
        "AND type='unbind_room' AND idempotency_key_hash=:key",
        owner=owner.bytes,
        key=hashlib.sha256(key.encode()).digest(),
    )
    if row and row["target_binding_id"] != binding.bytes:
        raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "幂等键已用于其他解绑目标")
    return UUID(bytes=row["id"]) if row else None


async def accept(state, principal, binding, key):
    async with state.database.connect() as conn:
        previous = await replay(conn, principal.user_id, binding, key)
    if previous:
        return previous
    if not state.side_effect_policy.school_binding_writes:
        raise ApiError(503, ErrorCode.FEATURE_DISABLED, "学校解绑尚未开放")
    credential = CredentialProof.model_validate(
        await state.service_client.call(
            "school_adapter",
            "/credentials/control-view",
            "credential:control-read",
            principal.request_id,
            principal=principal,
        )
    )
    if credential.state != "active" or not credential.use_allowed:
        raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "请先修复学校认证再解绑")
    async with state.database.begin() as conn:
        preference = await lock_preference(conn, principal.user_id)
        previous = await replay(conn, principal.user_id, binding, key)
        if previous:
            return previous
        if preference["removal_operation_id"] or preference["switch_operation_id"]:
            current = preference["removal_operation_id"] or preference["switch_operation_id"]
            raise ApiError(
                409,
                ErrorCode.OPERATION_IN_PROGRESS,
                "已有寝室更新正在进行",
                existing_operation_id=UUID(bytes=current),
            )
        target = await first(
            conn,
            "SELECT * FROM room_bindings WHERE id=:id AND owner_user_id=:owner "
            "AND status='active' FOR UPDATE",
            id=binding.bytes,
            owner=principal.user_id.bytes,
        )
        if not target:
            raise ApiError(404, ErrorCode.NOT_FOUND, "本人有效绑定不存在")
        pending = await first(
            conn,
            "SELECT id FROM room_operations WHERE owner_user_id=:owner "
            "AND open_binding_target=:room",
            owner=principal.user_id.bytes,
            room=target["room_id"],
        )
        if pending:
            raise ApiError(
                409,
                ErrorCode.OPERATION_IN_PROGRESS,
                "该目标仍有未解决的学校操作",
                existing_operation_id=UUID(bytes=pending["id"]),
            )
        return await register(conn, principal, target, preference, credential, key)


async def register(conn, principal, target, preference, credential, key):
    operation, upstream = new_id(), new_id()
    was_default = preference["default_binding_id"] == target["id"]
    await execute(
        conn,
        "INSERT INTO room_operations (id,owner_user_id,type,target_room_id,target_binding_id,"
        "idempotency_key_hash,request_digest,state,saga_step,upstream_operation_id,credential_ref,"
        "credential_version,binding_status,default_status,removal_was_default,"
        "expected_preference_version,"
        "next_reconcile_at) VALUES (:id,:owner,'unbind_room',:room,:binding,:key,:digest,"
        "'accepted',"
        "'removal_prepared',:upstream,:credential,:version,'pending',:status,:was_default,"
        ":preference,UTC_TIMESTAMP(6))",
        id=operation.bytes,
        owner=principal.user_id.bytes,
        room=target["room_id"],
        binding=target["id"],
        key=hashlib.sha256(key.encode()).digest(),
        digest=hashlib.sha256(target["id"]).digest(),
        upstream=upstream.bytes,
        credential=credential.credential_ref.bytes,
        version=credential.credential_version,
        status="switching" if was_default else "unchanged",
        was_default=was_default,
        preference=preference["version"],
    )
    await execute(
        conn,
        "UPDATE room_preferences SET removal_operation_id=:id,state=IF(:default,'switching',state),"
        "updated_at=UTC_TIMESTAMP(6) WHERE owner_user_id=:owner",
        id=operation.bytes,
        default=was_default,
        owner=principal.user_id.bytes,
    )
    # 让在途旧 B02 同步失去本域提交许可，解绑结束后也不能复活旧镜像。
    await execute(
        conn,
        "UPDATE room_operations SET state='cancelled',saga_step='removal_cancelled',"
        "lease_owner=NULL,lease_until=NULL,next_reconcile_at=NULL,updated_at=UTC_TIMESTAMP(6) "
        "WHERE owner_user_id=:owner AND type='binding_sync' AND state IN ('accepted','running')",
        owner=principal.user_id.bytes,
    )
    await execute(
        conn,
        "UPDATE room_sync_state SET state=IF(last_synced_at IS NULL,'failed','stale'),"
        "error_code='OPERATION_IN_PROGRESS' WHERE owner_user_id=:owner AND state='loading'",
        owner=principal.user_id.bytes,
    )
    await record_audit(
        conn,
        "room",
        "room.removal_accepted",
        "operation",
        operation,
        principal.request_id,
        actor=principal.user_id,
    )
    return operation


async def commit(engine, row, request_id):
    async with engine.begin() as conn:
        current = await locked_operation(conn, row)
        if not current:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "解绑操作租约已变化")
        if current["binding_status"] == "removed":
            return current["committed_preference_version"]
        preference = await lock_preference(conn, current["owner_user_id"])
        if preference["removal_operation_id"] != current["id"]:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "解绑操作槽已变化")
        await execute(
            conn,
            "UPDATE room_bindings SET status='inactive',updated_at=UTC_TIMESTAMP(6) "
            "WHERE id=:id AND owner_user_id=:owner",
            id=current["target_binding_id"],
            owner=current["owner_user_id"],
        )
        await execute(
            conn,
            "UPDATE room_balance_cache SET quality='stale',updated_at=UTC_TIMESTAMP(6) WHERE "
            "binding_id=:id",
            id=current["target_binding_id"],
        )
        version = None
        if current["removal_was_default"]:
            if (
                preference["default_binding_id"] != current["target_binding_id"]
                or preference["version"] != current["expected_preference_version"]
            ):
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "解绑默认偏好已变化")
            version = preference["version"] + 1
            await execute(
                conn,
                "UPDATE room_preferences SET default_binding_id=NULL,version=:version,"
                "state='blocked',"
                "updated_at=UTC_TIMESTAMP(6) WHERE owner_user_id=:owner",
                version=version,
                owner=current["owner_user_id"],
            )
        await execute(
            conn,
            "UPDATE room_operations SET binding_status='removed',"
            "committed_preference_version=:version,"
            "saga_step=:step,error_code=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            version=version,
            step="preference_committed" if version else "removal_committed",
            id=current["id"],
        )
        await record_audit(
            conn,
            "room",
            "room.binding_removed",
            "binding",
            UUID(bytes=current["target_binding_id"]),
            request_id,
            actor=UUID(bytes=current["owner_user_id"]),
            version=version or preference["version"],
        )
        return version


async def finish(engine, row, *, failed=False):
    async with engine.begin() as conn:
        current = await locked_operation(conn, row)
        if not current:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "解绑操作租约已变化")
        await execute(
            conn,
            "UPDATE room_preferences SET removal_operation_id=NULL,"
            "state=IF(default_binding_id IS NULL,'blocked','ready'),updated_at=UTC_TIMESTAMP(6) "
            "WHERE owner_user_id=:owner AND removal_operation_id=:id",
            owner=current["owner_user_id"],
            id=current["id"],
        )
        await execute(
            conn,
            "UPDATE room_operations SET state=:state,binding_status=:binding,"
            "default_status=:default,"
            "saga_step=:step,lease_owner=NULL,lease_until=NULL,next_reconcile_at=NULL,"
            "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            state="failed" if failed else "succeeded",
            binding="failed" if failed else "removed",
            default=("failed" if failed else "confirmed")
            if current["removal_was_default"]
            else "unchanged",
            step="compensated" if failed else "completed",
            id=current["id"],
        )
