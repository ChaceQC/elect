"""二维码刷新按本人全部订单计额；owner先于操作和订单锁。"""

from services.common.admission import enforce_budget
from services.common.sql import execute, first


async def lock_owner(conn, owner):
    await execute(conn, "INSERT INTO payment_owners (owner_user_id) VALUES (:owner) "
                  "ON DUPLICATE KEY UPDATE owner_user_id=owner_user_id", owner=owner.bytes)
    await first(conn, "SELECT owner_user_id FROM payment_owners "
                "WHERE owner_user_id=:owner FOR UPDATE", owner=owner.bytes)


async def check_budget(conn, owner):
    recent = await first(
        conn, "SELECT COUNT(*) AS daily,COALESCE(SUM(created_at>"
        "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 MINUTE)),0) AS minute,"
        "MIN(created_at) AS earliest,UTC_TIMESTAMP(6) AS now FROM payment_qr_requests "
        "WHERE owner_user_id=:owner AND created_at>DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 DAY)",
        owner=owner.bytes,
    )
    pending = await first(
        conn, "SELECT COUNT(*) AS n FROM payment_qr_requests q JOIN payment_operations o "
        "ON o.id=q.operation_id WHERE q.owner_user_id=:owner "
        "AND o.state NOT IN ('succeeded','failed','cancelled')", owner=owner.bytes,
    )
    enforce_budget(recent, pending["n"])
