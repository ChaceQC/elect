"""取消本地支付意图；不删除上游台账，不声称学校撤销或退款。"""

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first

from .orders import order_view
from .states import ORDER


async def settle_cancellations(engine):
    async with engine.begin() as conn:
        result = await execute(
            conn,
            "UPDATE payment_orders SET cancelled_at=UTC_TIMESTAMP(6),version=version+1 "
            "WHERE cancel_requested_at IS NOT NULL AND cancelled_at IS NULL "
            "AND cancel_after<=UTC_TIMESTAMP(6)",
        )
    return bool(result.rowcount)


async def cancel(engine, principal, order, expected_version):
    async with engine.begin() as conn:
        await first(
            conn,
            "SELECT owner_user_id FROM payment_owners WHERE owner_user_id=:owner FOR UPDATE",
            owner=principal.user_id.bytes,
        )
        await execute(
            conn,
            "SELECT id FROM payment_operations "
            "WHERE order_id=:id AND owner_user_id=:owner FOR UPDATE",
            id=order.bytes,
            owner=principal.user_id.bytes,
        )
        row = await first(
            conn,
            "SELECT * FROM payment_orders WHERE id=:id AND owner_user_id=:owner FOR UPDATE",
            id=order.bytes,
            owner=principal.user_id.bytes,
        )
        # 锁定订单后重新读取，覆盖此前已提交的二维码刷新/领取。
        operations = (
            await execute(
                conn,
                "SELECT *,lease_until>UTC_TIMESTAMP(6) AS in_flight FROM payment_operations "
                "WHERE order_id=:id AND owner_user_id=:owner FOR UPDATE",
                id=order.bytes,
                owner=principal.user_id.bytes,
            )
        ).mappings().all()
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "订单不存在")
        if row["state"] == "paid_confirmed":
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "学校已确认支付，取消不能退款")
        if row["cancel_requested_at"]:
            return order_view(row)
        if expected_version is None:
            raise ApiError(428, ErrorCode.PRECONDITION_REQUIRED, "取消前请读取订单版本")
        if row["version"] != expected_version:
            raise ApiError(
                409, ErrorCode.VERSION_CONFLICT, "订单已变化，请核对最新支付结果",
                current_version=row["version"],
            )
        if row["state"] in ORDER.terminal:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "订单已终结")
        after = max(
            (item["lease_until"] for item in operations
             if item["state"] == "running" and item["in_flight"]),
            default=None,
        )
        await execute(
            conn,
            "UPDATE payment_operations SET state='cancelled',execution_epoch=execution_epoch+1,"
            "lease_owner=NULL,lease_until=NULL,next_attempt_at=NULL "
            "WHERE order_id=:id AND state IN ('accepted','running','reconciling','unknown')",
            id=order.bytes,
        )
        await execute(
            conn,
            "UPDATE payment_orders SET cancel_requested_at=UTC_TIMESTAMP(6),"
            "cancel_after=COALESCE(:after,UTC_TIMESTAMP(6)),"
            "cancelled_at=IF(:after IS NULL,UTC_TIMESTAMP(6),NULL),"
            "next_check_at=NULL,version=version+1 WHERE id=:id",
            id=order.bytes,
            after=after,
        )
        await record_audit(
            conn, "payment", "payment.cancel_requested", "order", order,
            principal.request_id, actor=principal.user_id,
        )
        row = await first(conn, "SELECT * FROM payment_orders WHERE id=:id", id=order.bytes)
    return order_view(row)
