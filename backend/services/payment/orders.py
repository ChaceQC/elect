"""Payment 本库事务：请求摘要、未解决槽位和 Outbox 一同持久提交。"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.events import OrderRequestedPayload
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.outbox import append_event
from services.common.sql import aware, execute, first

from .dto import AcceptedOrder, Order, OrderReference
from .policy import validate_amount


def request_digest(command):
    return hashlib.sha256(command.model_dump_json(exclude={"idempotency_key"}).encode()).digest()


def key_hash(key):
    return hashlib.sha256(key.encode()).digest()


def reference(row):
    return OrderReference(
        order_id=UUID(bytes=row["id"]),
        binding_id=UUID(bytes=row["binding_id"]),
        state=row["state"],
        amount=format(row["amount"], ".2f"),
        currency=row["currency"],
        created_at=aware(row["created_at"]),
    )


def order_view(row):
    return Order(
        **reference(row).model_dump(),
        binding_display_name=row["binding_display_name"],
        paid_confirmed=row["state"] == "paid_confirmed",
        last_checked_at=aware(row["last_checked_at"]),
        qr_status=row["qr_status"],
        qr_expires_at=aware(row["qr_expires_at"]),
        error_code=row["error_code"],
        qr_error_code=row["qr_error_code"],
        balance_refresh_state=row["balance_refresh_state"],
        balance_refresh_operation_id=UUID(bytes=row["balance_refresh_operation_id"])
        if row["balance_refresh_operation_id"]
        else None,
    )


def accepted(row):
    order = UUID(bytes=row["id"])
    return AcceptedOrder(
        order_id=order, state=row["state"], poll_url=f"/api/v1/payment-orders/{order}"
    )


async def get_order(engine, owner, order):
    async with engine.connect() as conn:
        row = await first(
            conn,
            "SELECT * FROM payment_orders WHERE id=:id AND owner_user_id=:owner",
            id=order.bytes,
            owner=owner.bytes,
        )
    if not row:
        raise ApiError(404, ErrorCode.NOT_FOUND, "订单不存在")
    return row


async def unresolved(engine, owner, binding):
    async with engine.connect() as conn:
        return await first(
            conn,
            "SELECT * FROM payment_orders WHERE owner_user_id=:owner "
            "AND unresolved_binding_id=:binding",
            owner=owner.bytes,
            binding=binding.bytes,
        )


async def replay(engine, owner, command):
    async with engine.connect() as conn:
        row = await first(
            conn,
            "SELECT * FROM payment_orders WHERE owner_user_id=:owner AND idempotency_key_hash=:key",
            owner=owner.bytes,
            key=key_hash(command.idempotency_key),
        )
    if row and row["request_digest"] != request_digest(command):
        raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "该幂等键已用于不同订单请求")
    return row


async def create_order(engine, principal, command, binding, credential):
    amount = validate_amount(command.amount)
    async with engine.begin() as conn:
        await execute(
            conn,
            "INSERT INTO payment_owners (owner_user_id) VALUES (:owner) "
            "ON DUPLICATE KEY UPDATE owner_user_id=owner_user_id",
            owner=principal.user_id.bytes,
        )
        await first(
            conn,
            "SELECT owner_user_id FROM payment_owners WHERE owner_user_id=:owner FOR UPDATE",
            owner=principal.user_id.bytes,
        )
        prior = await first(
            conn,
            "SELECT * FROM payment_orders WHERE owner_user_id=:owner AND idempotency_key_hash=:key",
            owner=principal.user_id.bytes,
            key=key_hash(command.idempotency_key),
        )
        if prior:
            if prior["request_digest"] != request_digest(command):
                raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "该幂等键已用于不同订单请求")
            return accepted(prior)
        pending = await first(
            conn,
            "SELECT id FROM payment_orders WHERE owner_user_id=:owner "
            "AND unresolved_binding_id=:binding",
            owner=principal.user_id.bytes,
            binding=command.binding_id.bytes,
        )
        if pending:
            raise ApiError(
                409,
                ErrorCode.OPERATION_IN_PROGRESS,
                "此寝室已有未解决订单，请恢复原订单",
                existing_operation_id=UUID(bytes=pending["id"]),
            )
        order, upstream, operation = new_id(), new_id(), new_id()
        await execute(
            conn,
            "INSERT INTO payment_orders (id,owner_user_id,binding_id,"
            "binding_display_name,credential_ref,credential_version,amount,currency,"
            "idempotency_key_hash,request_digest,state,version,upstream_operation_id) "
            "VALUES (:id,:owner,:binding,:name,:credential,:version,:amount,'CNY',:key,"
            ":digest,'created',1,:upstream)",
            id=order.bytes,
            owner=principal.user_id.bytes,
            binding=command.binding_id.bytes,
            name=binding["display_name"],
            credential=UUID(credential["credential_ref"]).bytes,
            version=credential["credential_version"],
            amount=amount,
            key=key_hash(command.idempotency_key),
            digest=request_digest(command),
            upstream=upstream.bytes,
        )
        await execute(
            conn,
            "INSERT INTO payment_operations (id,owner_user_id,order_id,kind,"
            "request_digest,state,execution_epoch,next_attempt_at) "
            "VALUES (:id,:owner,:order,'create_order',:digest,'accepted',1,UTC_TIMESTAMP(6))",
            id=operation.bytes,
            owner=principal.user_id.bytes,
            order=order.bytes,
            digest=request_digest(command),
        )
        await append_event(
            conn,
            EventEnvelope(
                event_id=new_id(),
                type="payment.order_requested",
                schema_version=1,
                producer="payment",
                aggregate_id=order,
                aggregate_version=1,
                occurred_at=datetime.now(UTC),
                request_id=principal.request_id,
                dedupe_key=str(order),
                payload=OrderRequestedPayload(order_id=order, owner_user_id=principal.user_id),
            ),
        )
        await record_audit(
            conn,
            "payment",
            "payment.order_accepted",
            "order",
            order,
            principal.request_id,
            actor=principal.user_id,
        )
    return AcceptedOrder(
        order_id=order, state="created", poll_url=f"/api/v1/payment-orders/{order}"
    )
