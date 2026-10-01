"""B02 缓存更新逐房间匹配；账号合并仅合并请求。"""

from services.common.errors import ErrorCode
from services.common.sql import execute


async def update_balances(conn, owner, records, error):
    await execute(
        conn,
        "UPDATE room_balance_cache c JOIN room_bindings b ON b.id=c.binding_id "
        "SET c.quality='stale',c.error_code=:error WHERE b.owner_user_id=:owner",
        owner=owner,
        error=error or ErrorCode.SCHOOL_INVALID_RESPONSE,
    )
    if error:
        return
    for record in records:
        if record["balance"] is None:
            continue
        await execute(
            conn,
            "INSERT INTO room_balance_cache (binding_id,balance,fetched_at,source,quality) "
            "SELECT b.id,:balance,UTC_TIMESTAMP(6),'school_bound_rooms','fresh' "
            "FROM room_bindings b JOIN rooms r ON r.id=b.room_id "
            "WHERE b.owner_user_id=:owner AND b.status='active' AND r.school_room_id=:room "
            "ON DUPLICATE KEY UPDATE balance=:balance,fetched_at=UTC_TIMESTAMP(6),"
            "quality='fresh',error_code=NULL,updated_at=UTC_TIMESTAMP(6)",
            owner=owner,
            room=record["room_id"],
            balance=record["balance"],
        )


async def finish_operations(conn, root, records, error):
    operations = (
        (
            await execute(
                conn,
                "SELECT o.id,r.school_room_id,b.status FROM room_operations o "
                "JOIN room_bindings b ON b.id=o.target_binding_id JOIN rooms r ON r.id=b.room_id "
                "WHERE o.id=:id OR (o.upstream_operation_id=:id AND "
                "o.type='balance_refresh' AND o.saga_step='merged')",
                id=root,
            )
        )
        .mappings()
        .all()
    )
    valid_rooms = {record["room_id"] for record in records if record["balance"] is not None}
    for operation in operations:
        failure = error or (
            ErrorCode.SCHOOL_INVALID_RESPONSE
            if operation["school_room_id"] not in valid_rooms or operation["status"] != "active"
            else None
        )
        await execute(
            conn,
            "UPDATE room_operations SET state=:state,saga_step='complete',error_code=:error,"
            "lease_owner=NULL,lease_until=NULL,next_reconcile_at=NULL,"
            "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=operation["id"],
            state="failed" if failure else "succeeded",
            error=failure,
        )
