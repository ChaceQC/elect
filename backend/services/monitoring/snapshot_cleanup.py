"""过期快照小批量清理；父行锁与固定成员外键顺序不依赖级联删除。"""

from services.common.logging import log
from services.common.sql import execute, first

SNAPSHOT_BATCH = 4
MEMBER_BATCH = 1_000


async def cleanup_snapshots(engine):
    removed, parents = 0, 0
    async with engine.begin() as conn:
        rows = (await execute(
            conn, "SELECT id FROM sample_snapshots WHERE expires_at<=UTC_TIMESTAMP(6) "
            "ORDER BY expires_at,id LIMIT :limit FOR UPDATE SKIP LOCKED",
            limit=SNAPSHOT_BATCH,
        )).mappings().all()
        for row in rows:
            result = await execute(
                conn, "DELETE FROM sample_snapshot_items WHERE snapshot_id=:id "
                "ORDER BY position LIMIT :limit", id=row["id"], limit=MEMBER_BATCH - removed,
            )
            removed += result.rowcount
            remaining = await first(
                conn, "SELECT position FROM sample_snapshot_items WHERE snapshot_id=:id LIMIT 1",
                id=row["id"],
            )
            if not remaining:
                await execute(conn, "DELETE FROM sample_snapshots WHERE id=:id", id=row["id"])
                parents += 1
            if removed >= MEMBER_BATCH:
                break
    if removed or parents:
        log("snapshot_members_cleaned", service="monitoring", count=removed)
        log("snapshots_cleaned", service="monitoring", count=parents)
    return bool(rows)
