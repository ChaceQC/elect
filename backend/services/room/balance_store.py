"""B02缓存逐房间匹配；主任务结果持久后每批最多250个别名独立提交。"""

import json

from services.common.errors import ErrorCode
from services.common.sql import execute, first


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
    valid_rooms = {record["room_id"] for record in records if record["balance"] is not None}
    bindings = (await execute(conn, "SELECT b.id,r.school_room_id FROM room_bindings b "
        "JOIN rooms r ON r.id=b.room_id JOIN room_operations o ON o.owner_user_id=b.owner_user_id "
        "WHERE o.id=:id AND b.status='active'", id=root)).mappings().all()
    summary = {"valid_bindings": [row["id"].hex() for row in bindings
                                  if row["school_room_id"] in valid_rooms], "error": error}
    await execute(conn, "UPDATE room_operations SET balance_result=:result WHERE id=:id",
                  result=json.dumps(summary), id=root)
    await finish_batch(conn, root, summary)


async def finish_batch(conn, root, summary):
    # 旧版支付别名由领取器恢复为独立读取，不能继承旧根的成功或失败。
    operations = (await execute(conn, "SELECT o.id,o.target_binding_id FROM room_operations o "
        "JOIN room_operations root ON root.id=:id WHERE o.owner_user_id=root.owner_user_id "
        "AND o.type='balance_refresh' AND o.state IN ('accepted','running') "
        "AND (o.id=:id OR (o.upstream_operation_id=:id AND o.saga_step='merged' "
        "AND o.request_source<>'payment')) "
        "ORDER BY (o.id=:id) DESC,o.id LIMIT 250", id=root)).mappings().all()
    for operation in operations:
        failure = summary["error"] or (ErrorCode.SCHOOL_INVALID_RESPONSE
            if operation["target_binding_id"].hex() not in summary["valid_bindings"] else None)
        await execute(conn, "UPDATE room_operations SET state=:state,saga_step='complete',"
            "error_code=:error,lease_owner=NULL,lease_until=NULL,next_reconcile_at=NULL,"
            "updated_at=UTC_TIMESTAMP(6) WHERE id=:id", id=operation["id"],
            state="failed" if failure else "succeeded", error=failure)
    return bool(operations)


async def settle_aliases(engine):
    from .preference_store import lock_preference

    async with engine.begin() as conn:
        root = await first(conn, "SELECT r.id,r.owner_user_id FROM room_operations r "
            "JOIN room_operations a ON a.upstream_operation_id=r.id "
            "AND a.owner_user_id=r.owner_user_id AND a.type=r.type "
            "WHERE r.type='balance_refresh' AND r.state IN ('succeeded','failed') "
            "AND r.balance_result IS NOT NULL AND a.state IN ('accepted','running') "
            "AND a.saga_step='merged' AND a.request_source<>'payment' ORDER BY r.id LIMIT 1")
        if not root:
            return False
        await lock_preference(conn, root["owner_user_id"])
        row = await first(conn, "SELECT balance_result FROM room_operations WHERE id=:id "
                          "FOR UPDATE", id=root["id"])
        summary = row["balance_result"]
        if isinstance(summary, str):
            summary = json.loads(summary)
        return await finish_batch(conn, root["id"], summary)
