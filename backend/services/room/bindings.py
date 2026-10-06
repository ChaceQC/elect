"""绑定受理与确认，只把学校 B02 确认事实标为 active。"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.events import BindingConfirmedPayload
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope, VerifiedCandidate
from services.common.outbox import append_event
from services.common.sql import execute, first

from .defaults import initialize_default
from .mirror import confirm_binding, upsert_room
from .preference_store import lock_preference, locked_operation, require_no_removal


async def replay(conn, owner, key, candidate_id):
    row = await first(
        conn,
        "SELECT * FROM room_operations WHERE owner_user_id=:owner "
        "AND type='bind_room' AND idempotency_key_hash=:key",
        owner=owner.bytes,
        key=hashlib.sha256(key.encode()).digest(),
    )
    if row and row["request_digest"] != hashlib.sha256(candidate_id.encode()).digest():
        raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "幂等键已用于不同候选")
    return UUID(bytes=row["id"]) if row else None


async def accept(state, principal, candidate_id, key):
    async with state.database.connect() as conn:
        previous = await replay(conn, principal.user_id, key, candidate_id)
    if previous:
        return previous
    if not state.side_effect_policy.school_binding_writes:
        raise ApiError(503, ErrorCode.FEATURE_DISABLED, "新增学校绑定尚未开放")
    value = VerifiedCandidate.model_validate(
        await state.service_client.call(
            "school_adapter",
            "/rooms/candidate",
            "school:binding",
            principal.request_id,
            {"candidate_id": candidate_id},
            principal=principal,
        )
    )
    async with state.database.begin() as conn:
        preference = await lock_preference(conn, principal.user_id)
        previous = await replay(conn, principal.user_id, key, candidate_id)
        if previous:
            return previous
        require_no_removal(preference)
        room = await upsert_room(conn, value.record.model_dump())
        pending = await first(
            conn,
            "SELECT id FROM room_operations WHERE owner_user_id=:owner "
            "AND open_binding_target=:target",
            owner=principal.user_id.bytes,
            target=room["id"],
        )
        if pending:
            raise ApiError(
                409,
                ErrorCode.OPERATION_IN_PROGRESS,
                "该寝室已有待确认的绑定，请查询原操作",
                existing_operation_id=UUID(bytes=pending["id"]),
            )
        operation, upstream = new_id(), new_id()
        await execute(
            conn,
            "INSERT INTO room_operations (id,owner_user_id,type,target_room_id,"
            "idempotency_key_hash,request_digest,state,saga_step,upstream_operation_id,"
            "candidate_id,credential_ref,credential_version,binding_status,default_status,"
            "next_reconcile_at) "
            "VALUES (:id,:owner,'bind_room',:room,:key,:digest,'accepted','binding_prepared',"
            ":upstream,:candidate,:credential,:version,'pending','pending',UTC_TIMESTAMP(6))",
            id=operation.bytes,
            owner=principal.user_id.bytes,
            room=room["id"],
            key=hashlib.sha256(key.encode()).digest(),
            digest=hashlib.sha256(candidate_id.encode()).digest(),
            upstream=upstream.bytes,
            candidate=candidate_id,
            credential=value.credential_ref.bytes,
            version=value.credential_version,
        )
        await record_audit(
            conn,
            "room",
            "room.binding_accepted",
            "operation",
            operation,
            principal.request_id,
            actor=principal.user_id,
        )
    return operation


async def confirm(engine, row, record, request_id):
    async with engine.begin() as conn:
        current = await locked_operation(conn, row)
        if not current:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "绑定操作租约已变化")
        if current["binding_status"] == "confirmed":
            return
        room = await first(
            conn, "SELECT school_room_id FROM rooms WHERE id=:id", id=current["target_room_id"]
        )
        if record["room_id"] != room["school_room_id"]:
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校确认目标不一致")
        binding = await confirm_binding(conn, current["owner_user_id"], record,
                                        record.get("balance_observation"))
        owner = UUID(bytes=current["owner_user_id"])
        preference = await lock_preference(conn, owner)
        child = None
        if preference["default_binding_id"] is None:
            child = (
                UUID(bytes=preference["switch_operation_id"])
                if preference["switch_operation_id"]
                else await initialize_default(conn, owner, request_id)
            )
        await execute(
            conn,
            "UPDATE room_operations SET binding_status='confirmed',target_binding_id=:binding,"
            "default_status=:status,default_operation_id=:child,saga_step='default_wait',"
            "error_code=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            binding=binding,
            status="switching" if child else "unchanged",
            child=child.bytes if child else None,
            id=current["id"],
        )
        event_id = new_id()
        await append_event(
            conn,
            EventEnvelope(
                event_id=event_id,
                type="room.binding_confirmed",
                schema_version=1,
                aggregate_id=UUID(bytes=binding),
                aggregate_version=preference["version"],
                producer="room",
                occurred_at=datetime.now(UTC),
                dedupe_key=str(event_id),
                request_id=request_id,
                payload=BindingConfirmedPayload(
                    binding_id=UUID(bytes=binding),
                    owner_user_id=owner,
                    preference_version=preference["version"],
                ),
            ),
        )
        await record_audit(
            conn,
            "room",
            "room.binding_confirmed",
            "operation",
            UUID(bytes=row["id"]),
            request_id,
            actor=owner,
        )


async def finish_default(engine, row):
    async with engine.begin() as conn:
        current = await locked_operation(conn, row)
        if not current:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "绑定操作租约已变化")
        child = (
            await first(
                conn,
                "SELECT * FROM room_operations WHERE id=:id",
                id=current["default_operation_id"],
            )
            if current["default_operation_id"]
            else None
        )
        if child and child["state"] not in {"succeeded", "failed", "cancelled"}:
            return False
        await execute(
            conn,
            "UPDATE room_operations SET state='succeeded',saga_step='completed',"
            "default_status=:status,error_code=:error,next_reconcile_at=NULL,"
            "lease_owner=NULL,lease_until=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            status="confirmed"
            if child and child["state"] == "succeeded"
            else "failed"
            if child
            else "unchanged",
            error=child["error_code"] if child else None,
            id=current["id"],
        )
        return True


async def fail(engine, row, error):
    async with engine.begin() as conn:
        current = await locked_operation(conn, row)
        if not current:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "绑定操作租约已变化")
        await execute(
            conn,
            "UPDATE room_operations SET state='failed',binding_status='failed',"
            "default_status='unchanged',error_code=:error,saga_step='rejected',"
            "lease_owner=NULL,lease_until=NULL,next_reconcile_at=NULL,updated_at=UTC_TIMESTAMP(6) "
            "WHERE id=:id",
            error=error,
            id=current["id"],
        )
