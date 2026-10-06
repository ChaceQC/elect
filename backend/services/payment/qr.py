"""二维码操作幂等与原订单恢复；刷新没有建单权限。"""

import hashlib
from uuid import UUID

from services.common.archive_store import request_key, unavailable
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.operations import AcceptedOperation, Operation
from services.common.sql import aware, execute, first

from .orders import get_order, key_hash
from .qr_admission import check_budget, lock_owner


async def operation(engine, owner, operation_id):
    async with engine.connect() as conn:
        row = await first(
            conn,
            "SELECT o.*,p.binding_id FROM payment_operations o JOIN payment_orders p "
            "ON p.id=o.order_id WHERE o.id=:id AND o.owner_user_id=:owner "
            "AND o.kind IN ('create_order','qr_refresh')",
            id=operation_id.bytes,
            owner=owner.bytes,
        )
    if not row:
        raise ApiError(404, ErrorCode.NOT_FOUND, "操作不存在")
    return Operation(
        id=operation_id,
        type="qr_refresh",
        state=row["state"],
        target_binding_id=UUID(bytes=row["binding_id"]),
        created_at=aware(row["created_at"]),
        binding_status=None,
        default_status=None,
        retryable=row["state"] == "failed",
        error_code=row["error_code"],
        next_reconcile_at=aware(row["next_attempt_at"])
        if row["state"] in {"accepted", "running", "reconciling", "unknown"}
        else None,
        result_binding_id=None,
        result_order_id=UUID(bytes=row["order_id"]),
    )


async def refresh(engine, owner, order, key):
    await get_order(engine, owner, order)
    digest = hashlib.sha256(f"qr:{order}".encode()).digest()
    async with engine.begin() as conn:
        await lock_owner(conn, owner)
        cold = await request_key(conn, owner, "qr_refresh", key_hash(key), digest)
        if cold:
            prior = await first(conn, "SELECT id,state FROM payment_operations "
                "WHERE id=:id AND owner_user_id=:owner AND order_id=:order",
                id=cold, owner=owner.bytes, order=order.bytes)
            if not prior:
                raise unavailable()
            return AcceptedOperation(operation_id=UUID(bytes=cold), state=prior["state"],
                                     poll_url=f"/api/v1/operations/{UUID(bytes=cold)}")
        # 与回查/Worker一致先锁操作，避免持订单锁后引用被回查锁住的操作。
        await execute(
            conn, "SELECT id FROM payment_operations WHERE order_id=:id FOR UPDATE",
            id=order.bytes,
        )
        row = await first(
            conn,
            "SELECT * FROM payment_orders WHERE id=:id AND owner_user_id=:owner FOR UPDATE",
            id=order.bytes,
            owner=owner.bytes,
        )
        if row["cancel_requested_at"]:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "支付已取消，不能继续获取二维码")
        previous = await first(
            conn,
            "SELECT q.*,o.state FROM payment_qr_requests q JOIN payment_operations o "
            "ON o.id=q.operation_id WHERE q.owner_user_id=:owner AND q.key_hash=:key",
            owner=owner.bytes,
            key=key_hash(key),
        )
        if previous:
            if previous["request_digest"] != digest:
                raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "该键已用于另一个二维码请求")
            operation_id, state = UUID(bytes=previous["operation_id"]), previous["state"]
        else:
            await check_budget(conn, owner)
            if row["state"] not in {"awaiting_payment", "status_unknown"}:
                raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "订单状态不允许重新取得二维码")
            pending = await first(
                conn,
                "SELECT id,state FROM payment_operations WHERE open_order_id=:order",
                order=order.bytes,
            )
            if pending:
                operation_id, state = UUID(bytes=pending["id"]), pending["state"]
            else:
                operation_id, state = new_id(), "accepted"
                await execute(
                    conn,
                    "INSERT INTO payment_operations (id,owner_user_id,order_id,kind,"
                    "idempotency_key_hash,request_digest,state,execution_epoch,next_attempt_at) "
                    "VALUES "
                    "(:id,:owner,:order,'qr_refresh',:key,:digest,'accepted',1,UTC_TIMESTAMP(6))",
                    id=operation_id.bytes,
                    owner=owner.bytes,
                    order=order.bytes,
                    key=key_hash(key),
                    digest=digest,
                )
                await execute(
                    conn,
                    "UPDATE payment_orders SET "
                    "qr_status='generating',qr_error_code=NULL WHERE id=:id",
                    id=order.bytes,
                )
            await execute(
                conn,
                "INSERT INTO payment_qr_requests "
                "(owner_user_id,key_hash,request_digest,operation_id) "
                "VALUES (:owner,:key,:digest,:id)",
                owner=owner.bytes,
                key=key_hash(key),
                digest=digest,
                id=operation_id.bytes,
            )
    return AcceptedOperation(
        operation_id=operation_id, state=state, poll_url=f"/api/v1/operations/{operation_id}"
    )
