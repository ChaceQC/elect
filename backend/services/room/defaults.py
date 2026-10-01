"""默认切换受理和本域提交；Monitoring 确认前保留 switching 与操作引用。"""

from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .preference_store import lock_preference, locked_operation, require_no_removal


async def accept_default(conn, owner, target, expected, request_id):
    preference = await lock_preference(conn, owner)
    require_no_removal(preference)
    if preference["switch_operation_id"]:
        previous = await first(
            conn, "SELECT * FROM room_operations WHERE id=:id", id=preference["switch_operation_id"]
        )
        if (
            previous["target_binding_id"] == target.bytes
            and previous["expected_preference_version"] == expected
        ):
            return UUID(bytes=previous["id"])
        raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "默认寝室正在切换，请等待当前结果")
    if preference["version"] != expected:
        raise ApiError(
            409,
            ErrorCode.VERSION_CONFLICT,
            "默认偏好已变化，请刷新后重试",
            current_version=preference["version"],
        )
    binding = await first(
        conn,
        "SELECT id FROM room_bindings WHERE id=:id AND owner_user_id=:owner AND status='active' "
        "FOR UPDATE",
        id=target.bytes,
        owner=owner.bytes,
    )
    if not binding:
        raise ApiError(404, ErrorCode.NOT_FOUND, "目标寝室不可用或不属于本人")
    if preference["default_binding_id"] == target.bytes:
        return None
    operation = new_id()
    await execute(
        conn,
        "INSERT INTO room_operations (id,owner_user_id,type,target_binding_id,request_digest,"
        "state,saga_step,expected_preference_version,next_reconcile_at) "
        "VALUES "
        "(:id,:owner,'switch_default',:target,:digest,'accepted','room_prepared',:version,UTC_TIMESTAMP(6))",
        id=operation.bytes,
        owner=owner.bytes,
        target=target.bytes,
        digest=target.bytes.ljust(32, b"\x00"),
        version=expected,
    )
    await execute(
        conn,
        "UPDATE room_preferences SET "
        "state='switching',switch_operation_id=:id,updated_at=UTC_TIMESTAMP(6) WHERE "
        "owner_user_id=:owner",
        id=operation.bytes,
        owner=owner.bytes,
    )
    await record_audit(
        conn, "room", "room.default_accepted", "operation", operation, request_id, actor=owner
    )
    return operation


async def initialize_default(conn, owner, request_id):
    preference = await lock_preference(conn, owner)
    if (
        preference["default_binding_id"]
        or preference["switch_operation_id"]
        or preference["removal_operation_id"]
        or preference["state"] == "blocked"
    ):
        return None
    first_binding = await first(
        conn,
        "SELECT b.id FROM room_bindings b JOIN rooms r ON r.id=b.room_id "
        "WHERE b.owner_user_id=:owner AND b.status='active' ORDER BY r.school_room_id,b.id LIMIT 1",
        owner=owner.bytes,
    )
    if not first_binding:
        return None
    return await accept_default(
        conn, owner, UUID(bytes=first_binding["id"]), preference["version"], request_id
    )


async def commit_preference(engine, row, request_id):
    async with engine.begin() as conn:
        current = await locked_operation(conn, row)
        if not current:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "操作租约已变化")
        if current["committed_preference_version"]:
            return current["committed_preference_version"]
        preference = await lock_preference(conn, row["owner_user_id"])
        binding = await first(
            conn,
            "SELECT id FROM room_bindings WHERE id=:id AND owner_user_id=:owner AND "
            "status='active' FOR UPDATE",
            id=current["target_binding_id"],
            owner=current["owner_user_id"],
        )
        if not binding:
            raise ApiError(404, ErrorCode.NOT_FOUND, "目标绑定已失效，正在恢复原目标")
        if (
            preference["switch_operation_id"] != current["id"]
            or preference["version"] != current["expected_preference_version"]
        ):
            raise ApiError(409, ErrorCode.VERSION_CONFLICT, "默认偏好已变化")
        version = preference["version"] + 1
        await execute(
            conn,
            "UPDATE room_preferences SET "
            "default_binding_id=:target,version=:version,updated_at=UTC_TIMESTAMP(6) WHERE "
            "owner_user_id=:owner",
            target=current["target_binding_id"],
            version=version,
            owner=current["owner_user_id"],
        )
        await execute(
            conn,
            "UPDATE room_operations SET "
            "saga_step='preference_committed',committed_preference_version=:version,"
            "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            version=version,
            id=current["id"],
        )
        await record_audit(
            conn,
            "room",
            "room.default_committed",
            "operation",
            UUID(bytes=current["id"]),
            request_id,
            actor=UUID(bytes=current["owner_user_id"]),
            version=version,
        )
        return version
