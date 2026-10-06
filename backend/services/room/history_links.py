"""历史别名只跟随同用户、同绑定且没有上游的直接根任务。"""

from services.common.sql import execute, first

OPEN = "('accepted','running','reconciling','unknown')"


async def root_operation(conn, sync_id):
    return await first(
        conn, "SELECT o.* FROM history_syncs s JOIN room_operations o ON o.id=s.operation_id "
        "WHERE s.id=:sync AND s.source='C02' AND o.type='history_sync' "
        "AND o.owner_user_id=s.owner_user_id AND o.target_binding_id=s.binding_id "
        "AND o.upstream_operation_id IS NULL", sync=sync_id,
    )


async def propagate(conn, sync_id, state, error):
    root = await root_operation(conn, sync_id)
    if not root:
        return
    # 两次更新避免OR迫使全表扫描；别名使用现有(owner,type,...)索引前缀。
    for condition in ("id=:root", "upstream_operation_id=:root AND id<>:root AND NOT EXISTS "
                      "(SELECT 1 FROM history_syncs s WHERE s.operation_id=room_operations.id)"):
        await execute(
            conn, "UPDATE room_operations SET state=:state,error_code=:error,"
            "saga_step=IF(:state='running','read_school','complete'),"
            "next_reconcile_at=IF(:state='running',UTC_TIMESTAMP(6),NULL),"
            "updated_at=UTC_TIMESTAMP(6) WHERE " + condition + " AND owner_user_id=:owner "
            "AND type='history_sync' AND target_binding_id=:binding "
            "AND target_room_id=:room AND state IN " + OPEN,
            root=root["id"], owner=root["owner_user_id"], binding=root["target_binding_id"],
            room=root["target_room_id"], state=state, error=error,
        )
