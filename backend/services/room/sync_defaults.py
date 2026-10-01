"""成功学校快照为绑定事实来源；默认仍有效就保留，否则选择学校第一项。"""

from uuid import UUID

from services.common.sql import first

from .defaults import accept_default
from .preference_store import lock_preference


async def align_default(conn, owner, target, request_id):
    preference = await lock_preference(conn, owner)
    if preference["switch_operation_id"] or preference["removal_operation_id"]:
        return None
    if preference["default_binding_id"]:
        current = await first(
            conn, "SELECT id FROM room_bindings WHERE id=:id AND owner_user_id=:owner "
            "AND status='active'",
            id=preference["default_binding_id"], owner=owner.bytes,
        )
        if current:
            return None
    return await accept_default(conn, owner, target, preference["version"], request_id)


async def snapshot_target(conn, owner, records):
    if not records:
        return None
    row = await first(
        conn, "SELECT b.id FROM room_bindings b JOIN rooms r ON r.id=b.room_id "
        "WHERE b.owner_user_id=:owner AND b.status='active' AND r.school_room_id=:room",
        owner=owner.bytes, room=records[0]["room_id"],
    )
    return UUID(bytes=row["id"])


async def realign_after_switch(conn, owner, request_id):
    snapshot = await first(
        conn, "SELECT target_binding_id FROM room_operations WHERE owner_user_id=:owner "
        "AND type='binding_sync' AND state='succeeded' ORDER BY created_at DESC,id DESC LIMIT 1",
        owner=owner.bytes,
    )
    if snapshot is None:
        return
    target = await first(
        conn, "SELECT b.id FROM room_bindings b JOIN rooms r ON r.id=b.room_id "
        "WHERE b.owner_user_id=:owner AND b.status='active' "
        "ORDER BY (b.id=:preferred) DESC,r.school_room_id,b.id LIMIT 1",
        owner=owner.bytes, preferred=snapshot["target_binding_id"],
    )
    await align_default(conn, owner, UUID(bytes=target["id"]) if target else None, request_id)
