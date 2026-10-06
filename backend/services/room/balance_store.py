"""B02 缓存更新逐房间匹配；账号合并仅合并请求。"""

from services.common.errors import ErrorCode
from services.common.sql import execute


async def update_balances(conn, owner, records, error, observation=None):
    from .balance_observations import apply_observation

    if observation is None:
        return
    rows = (await execute(
        conn, "SELECT b.id,b.status,r.school_room_id FROM room_bindings b "
        "JOIN rooms r ON r.id=b.room_id WHERE b.owner_user_id=:owner", owner=owner,
    )).mappings().all()
    values = {record["room_id"]: record["balance"] for record in records}
    for row in rows:
        amount = values.get(row["school_room_id"]) if row["status"] == "active" else None
        await apply_observation(conn, row["id"], amount, observation, error)


async def finish_operations(conn, root, records, error):
    after = b""
    valid_rooms = {record["room_id"] for record in records if record["balance"] is not None}
    while True:
        operations = await operation_batch(conn, root, after)
        if not operations:
            break
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
                id=operation["id"], state="failed" if failure else "succeeded", error=failure,
            )
        after = operations[-1]["id"]


async def operation_batch(conn, root, after):
    return (
        (
            await execute(
                conn,
                "SELECT o.id,r.school_room_id,b.status FROM room_operations o "
                "JOIN room_bindings b ON b.id=o.target_binding_id JOIN rooms r ON r.id=b.room_id "
                "JOIN room_operations root ON root.id=:id "
                "WHERE o.id>:after AND o.owner_user_id=root.owner_user_id AND "
                "o.type='balance_refresh' AND (o.id=:id OR (o.upstream_operation_id=:id AND "
                "o.state IN ('accepted','running') AND o.saga_step='merged')) "
                "ORDER BY o.id LIMIT 250",
                id=root, after=after,
            )
        )
        .mappings()
        .all()
    )
