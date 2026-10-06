"""手动映射及终态尝试归档；run保留为查询/样本/调度唯一键的稳定索引。"""

from services.common import archive_store
from services.common.retention import TERMINAL, cutoff_time
from services.common.retention_cursor import scan
from services.common.sql import execute


async def archive(conn, kind, cutoff, *, apply=False, limit=200, after=""):
    boundary = await cutoff_time(conn, cutoff)
    if kind == "monitor_run_requests":
        where, order, params = scan(("q.owner_user_id", "q.idempotency_key_hash"), after)
        rows = (await execute(conn, "SELECT q.* FROM monitor_run_requests q "
            f"JOIN monitor_runs r ON r.id=q.run_id WHERE r.state IN {TERMINAL} "
            "AND r.lease_owner IS NULL AND r.lease_until IS NULL "
            "AND r.updated_at<=:cutoff AND q.created_at<=:cutoff "
            "AND GREATEST(q.expires_at,DATE_ADD(q.created_at,INTERVAL 180 DAY))<=UTC_TIMESTAMP(6) "
            f"AND {where} ORDER BY {order} LIMIT :limit FOR UPDATE SKIP LOCKED",
            cutoff=boundary, limit=limit, **params)).mappings().all()
        cursor = (rows[-1]["owner_user_id"].hex()+":"+rows[-1]["idempotency_key_hash"].hex()
                  if rows else after)
        if apply:
            for row in rows:
                key = row["owner_user_id"].hex() + ":" + row["idempotency_key_hash"].hex()
                record = await archive_store.save(conn, kind, key, row)
                await archive_store.retain_key(conn, row["owner_user_id"], "manual_run",
                    row["idempotency_key_hash"], row["request_digest"], row["run_id"], record)
                await execute(conn, "DELETE FROM monitor_run_requests WHERE owner_user_id=:owner "
                    "AND idempotency_key_hash=:key", owner=row["owner_user_id"],
                    key=row["idempotency_key_hash"])
    elif kind == "monitor_attempts":
        rows = (await execute(conn, "SELECT a.* FROM monitor_attempts a JOIN monitor_runs r "
            f"ON r.id=a.run_id WHERE r.state IN {TERMINAL} AND r.updated_at<=:cutoff "
            "AND r.lease_owner IS NULL AND r.lease_until IS NULL AND a.finished_at<=:cutoff "
            "AND a.created_at<=:cutoff AND a.id>:after ORDER BY a.id LIMIT :limit "
            "FOR UPDATE SKIP LOCKED", cutoff=boundary, limit=limit,
            after=bytes.fromhex(after))).mappings().all()
        cursor = rows[-1]["id"].hex() if rows else after
        if apply:
            for row in rows:
                await archive_store.save(conn, kind, row["run_id"].hex()+":"+row["id"].hex(), row)
                await execute(conn, "DELETE FROM monitor_attempts WHERE id=:id", id=row["id"])
    else:
        raise ValueError("Monitoring归档类别未登记")
    return {"candidates": len(rows), "archived": len(rows) if apply else 0,
            "retained": 0, "cursor": cursor}
