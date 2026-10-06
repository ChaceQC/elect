"""仅归档终态只读操作；实际FK和稳定合并/恢复引用继续保护热行。"""

from services.common import archive_store
from services.common.retention import TERMINAL, cutoff_time, foreign_references
from services.common.sql import execute, first


async def archive(conn, kind, cutoff, *, apply=False, limit=200, after=""):
    if kind != "room_operations":
        raise ValueError("Room归档类别未登记")
    boundary = await cutoff_time(conn, cutoff)
    rows = (await execute(conn, "SELECT * FROM room_operations WHERE type IN "
        f"('balance_refresh','history_sync') AND state IN {TERMINAL} "
        "AND created_at<=:cutoff AND updated_at<=:cutoff AND lease_owner IS NULL "
        "AND lease_until IS NULL AND next_reconcile_at IS NULL "
        "AND id>:after ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED",
        cutoff=boundary, limit=limit, after=bytes.fromhex(after))).mappings().all()
    retained, eligible = 0, 0
    for row in rows:
        if await foreign_references(conn, kind, row) or await first(conn,
            "SELECT id FROM room_operations WHERE upstream_operation_id=:id AND id<>:id LIMIT 1",
            id=row["id"]):
            retained += 1
            continue
        eligible += 1
        if apply:
            archive = await archive_store.save(conn, kind, row["id"].hex(), row)
            if row["idempotency_key_hash"] is not None:
                await archive_store.retain_key(conn, row["owner_user_id"], row["type"],
                    row["idempotency_key_hash"], row["request_digest"], row["id"], archive)
            await execute(conn, "DELETE FROM room_operations WHERE id=:id", id=row["id"])
    return {"candidates": len(rows), "eligible": eligible,
            "archived": eligible if apply else 0, "retained": retained,
            "cursor": rows[-1]["id"].hex() if rows else after}
