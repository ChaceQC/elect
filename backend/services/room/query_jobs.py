"""只读学校操作受理：本域账号锁、幂等重放与合并。"""

import hashlib
from uuid import UUID

from services.common.archive_store import request_key
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .preference_store import lock_preference, require_no_removal


async def target(conn, owner, binding, *, active=False):
    row = await first(
        conn,
        "SELECT b.*,r.school_room_id,CONCAT(r.building_name,'-',r.room_no) AS display_name "
        "FROM room_bindings b "
        "JOIN rooms r ON r.id=b.room_id "
        "WHERE b.id=:id AND b.owner_user_id=:owner",
        id=binding.bytes,
        owner=owner.bytes,
    )
    if not row or active and row["status"] != "active":
        raise ApiError(404, ErrorCode.NOT_FOUND, "本人有效绑定不存在")
    return row


async def accept_query(conn, owner, binding, key, kind, digest, *,
                       admission=None, source="browser"):
    preference = await lock_preference(conn, owner)
    key_hash = hashlib.sha256(key.encode()).digest()
    prior = await first(
        conn,
        "SELECT * FROM room_operations WHERE owner_user_id=:owner AND type=:type "
        "AND idempotency_key_hash=:key",
        owner=owner.bytes,
        type=kind,
        key=key_hash,
    )
    if prior:
        if prior["request_digest"] != digest:
            raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "同一幂等键的请求内容不同")
        return UUID(bytes=prior["id"]), False
    cold = await request_key(conn, owner, kind, key_hash, digest)
    if cold:
        return UUID(bytes=cold), False
    require_no_removal(preference)
    row = await target(conn, owner, binding, active=True)
    if admission is not None:
        await admission(conn)
    operation = new_id()
    await execute(
        conn,
        "INSERT INTO room_operations (id,owner_user_id,type,target_room_id,target_binding_id,"
        "idempotency_key_hash,request_digest,request_source,state,saga_step,next_reconcile_at) "
        "VALUES (:id,:owner,:type,:room,:binding,:key,:digest,:source,'accepted','read_school',"
        "UTC_TIMESTAMP(6))",
        id=operation.bytes,
        owner=owner.bytes,
        type=kind,
        room=row["room_id"],
        binding=binding.bytes,
        key=key_hash,
        digest=digest,
        source=source,
    )
    return operation, True
