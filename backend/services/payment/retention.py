"""只归档已终结的二维码请求映射；订单、操作与发送/unknown证据保持。"""

from services.common import archive_store
from services.common.retention import TERMINAL, cutoff_time
from services.common.retention_cursor import scan
from services.common.sql import execute


async def archive(conn, kind, cutoff, *, apply=False, limit=200, after=""):
    if kind != "payment_qr_requests":
        raise ValueError("Payment归档类别未登记")
    where, order, params = scan(("q.owner_user_id", "q.key_hash"), after)
    rows = (await execute(conn, "SELECT q.* FROM payment_qr_requests q "
        "JOIN payment_operations o ON o.id=q.operation_id JOIN payment_orders p ON p.id=o.order_id "
        f"WHERE o.state IN {TERMINAL} AND o.lease_owner IS NULL AND o.lease_until IS NULL "
        "AND p.state IN ('paid_confirmed','rejected','expired_confirmed','closed_confirmed') "
        "AND p.balance_refresh_state<>'pending' AND p.next_check_at IS NULL "
        "AND o.updated_at<=:cutoff AND q.created_at<=:cutoff "
        f"AND {where} ORDER BY {order} LIMIT :limit FOR UPDATE SKIP LOCKED",
        cutoff=await cutoff_time(conn, cutoff), limit=limit, **params)).mappings().all()
    if apply:
        for row in rows:
            key = row["owner_user_id"].hex() + ":" + row["key_hash"].hex()
            archive = await archive_store.save(conn, kind, key, row)
            await archive_store.retain_key(conn, row["owner_user_id"], "qr_refresh",
                row["key_hash"], row["request_digest"], row["operation_id"], archive)
            await execute(conn, "DELETE FROM payment_qr_requests WHERE owner_user_id=:owner "
                          "AND key_hash=:key", owner=row["owner_user_id"], key=row["key_hash"])
    cursor = rows[-1]["owner_user_id"].hex()+":"+rows[-1]["key_hash"].hex() if rows else after
    return {"candidates": len(rows), "archived": len(rows) if apply else 0,
            "retained": 0, "cursor": cursor}
