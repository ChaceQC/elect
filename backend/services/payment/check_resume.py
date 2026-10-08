"""本人显式恢复原订单；重放不延长活动窗口，不生成学校发送标识。"""

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first

from .check_window import WINDOW_SECONDS, expired, in_flight
from .orders import order_view
from .states import ORDER


async def resume(engine, principal, order, expected_version):
    async with engine.begin() as conn:
        await first(conn, "SELECT owner_user_id FROM payment_owners "
                    "WHERE owner_user_id=:owner FOR UPDATE", owner=principal.user_id.bytes)
        operations = (await execute(
            conn, "SELECT *,lease_until>UTC_TIMESTAMP(6) AS in_flight FROM payment_operations "
            "WHERE order_id=:id AND owner_user_id=:owner FOR UPDATE",
            id=order.bytes, owner=principal.user_id.bytes,
        )).mappings().all()
        row = await first(conn, "SELECT *,UTC_TIMESTAMP(6) AS observed_at FROM payment_orders "
                          "WHERE id=:id AND owner_user_id=:owner FOR UPDATE",
                          id=order.bytes, owner=principal.user_id.bytes)
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "订单不存在")
        if row["cancel_requested_at"] or row["state"] in ORDER.terminal:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "订单已停止处理或已终结")
        if expected_version is None:
            raise ApiError(428, ErrorCode.PRECONDITION_REQUIRED, "恢复前请读取订单版本")
        if not expired(row):
            return order_view(row)
        if row["version"] != expected_version:
            raise ApiError(409, ErrorCode.VERSION_CONFLICT, "订单已变化，请核对最新支付结果",
                           current_version=row["version"])
        running = any(item["state"] == "running" and item["in_flight"] for item in operations)
        if running or in_flight(row):
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "本次处理尚未结束，请稍后恢复")
        await execute(
            conn, "UPDATE payment_orders SET "
            "check_deadline_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL :window SECOND),"
            "next_check_at=IF(state IN ('awaiting_payment','status_unknown','submit_unknown'),"
            "UTC_TIMESTAMP(6),NULL),version=version+1,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=order.bytes, window=WINDOW_SECONDS,
        )
        await execute(
            conn, "UPDATE payment_operations SET state=IF(state='running','reconciling',state),"
            "lease_owner=NULL,lease_until=NULL,next_attempt_at=UTC_TIMESTAMP(6) "
            "WHERE order_id=:id AND state IN ('accepted','running','reconciling','unknown')",
            id=order.bytes,
        )
        await record_audit(conn, "payment", "payment.check_resumed", "order", order,
                           principal.request_id, actor=principal.user_id)
        row = await first(conn, "SELECT * FROM payment_orders WHERE id=:id", id=order.bytes)
    return order_view(row)
