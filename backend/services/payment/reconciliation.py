"""只接受 Adapter 已验收映射；付款后重新查询学校余额，不做本地加法。"""

import asyncio
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first

from .states import ORDER


async def claim(engine, order_id=None):
    lease = str(new_id())
    async with engine.begin() as conn:
        row = await first(
            conn,
            "SELECT * FROM payment_orders WHERE next_check_at<=UTC_TIMESTAMP(6) "
            "AND (check_lease_until IS NULL OR check_lease_until<=UTC_TIMESTAMP(6)) "
            "AND (:order IS NULL OR id=:order) "
            "AND (cancel_requested_at IS NULL OR state='paid_confirmed') "
            "AND (state IN ('awaiting_payment','status_unknown','submit_unknown') OR "
            "(state='paid_confirmed' AND balance_refresh_state IN ('pending','failed'))) "
            "ORDER BY next_check_at,id LIMIT 1 FOR UPDATE SKIP LOCKED",
            order=order_id.bytes if order_id else None,
        )
        if not row:
            return None
        await execute(
            conn,
            "UPDATE payment_orders SET check_lease_owner=:lease,"
            "check_lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 SECOND) WHERE id=:id",
            id=row["id"],
            lease=lease,
        )
    return {**row, "check_lease_owner": lease}


async def balance_refresh(state, row, principal):
    operation = row["balance_refresh_operation_id"]
    if not operation:
        value = await state.service_client.call(
            "room",
            "/browser/balance-refresh",
            "room:browser",
            principal.request_id,
            {
                "binding_id": str(UUID(bytes=row["binding_id"])),
                "idempotency_key": f"payment-paid:{UUID(bytes=row['id'])}",
            },
            principal=principal,
        )
        operation = UUID(value["operation_id"]).bytes
    value = await state.service_client.call(
        "room",
        "/browser/operation",
        "room:browser",
        principal.request_id,
        {"operation_id": str(UUID(bytes=operation))},
        principal=principal,
    )
    return operation, "succeeded" if value["state"] == "succeeded" else "failed" if value[
        "state"
    ] in {"failed", "cancelled"} else "pending"


async def check_order(app, row):
    state = app.state
    principal = Principal("payment", UUID(bytes=row["owner_user_id"]), 1, new_id())
    next_state, error = row["state"], None
    refresh_state, operation = row["balance_refresh_state"], row["balance_refresh_operation_id"]
    try:
        if row["state"] != "paid_confirmed":
            value = await state.service_client.call(
                "school_adapter",
                "/payments/check",
                "school:payment",
                principal.request_id,
                {"order_id": str(UUID(bytes=row["id"]))},
                principal=principal,
            )
            candidate = value.get("order_state", next_state)
            error = value.get("error_code")
            if candidate != next_state and candidate in ORDER.transitions[next_state]:
                next_state = candidate
            if next_state == "paid_confirmed":
                refresh_state = "pending"
        if next_state == "paid_confirmed" and refresh_state != "succeeded":
            operation, refresh_state = await balance_refresh(state, row, principal)
    except ApiError as failure:
        error = failure.code
        if next_state == "paid_confirmed":
            refresh_state = "failed"
    async with state.database.begin() as conn:
        # 与建单/取码提交及取消统一按操作→订单加锁，避免独立回查角色反向抢锁。
        await execute(
            conn, "SELECT id FROM payment_operations WHERE order_id=:id FOR UPDATE",
            id=row["id"],
        )
        valid = await first(
            conn,
            "SELECT * FROM payment_orders WHERE id=:id AND "
            "check_lease_owner=:lease AND check_lease_until>UTC_TIMESTAMP(6) FOR UPDATE",
            id=row["id"],
            lease=row["check_lease_owner"],
        )
        if not valid or valid["state"] in ORDER.terminal and valid["state"] != "paid_confirmed":
            return
        # 其他请求不能使已确认付款退回未知；过期 lease 的结果也不提交。
        if valid["state"] == "paid_confirmed":
            next_state = "paid_confirmed"
        await execute(
            conn,
            "UPDATE payment_orders SET state=:state,error_code=:error,"
            "last_checked_at=UTC_TIMESTAMP(6),"
            "next_check_at=IF(cancel_requested_at IS NOT NULL AND :state!='paid_confirmed',"
            "NULL,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL :delay SECOND)),"
            "check_lease_owner=NULL,check_lease_until=NULL,balance_refresh_state=:refresh,"
            "balance_refresh_operation_id=:operation,version=version+1 WHERE id=:id",
            id=row["id"],
            state=next_state,
            error=error,
            refresh=refresh_state,
            operation=operation,
            delay=30 if error else 2,
        )
        if next_state in ORDER.terminal and valid["state"] != next_state:
            await execute(
                conn,
                "UPDATE payment_operations SET state='succeeded',lease_owner=NULL,lease_until=NULL "
                "WHERE order_id=:id AND state IN ('accepted','running','reconciling','unknown')",
                id=row["id"],
            )
            await record_audit(
                conn,
                "payment",
                f"payment.{next_state}",
                "order",
                UUID(bytes=row["id"]),
                principal.request_id,
                actor=principal.user_id,
            )


async def check_tick(app, heartbeat=None, order_id=None):
    row = await claim(app.state.database, order_id)
    if not row:
        return False
    task = asyncio.create_task(check_order(app, row))
    try:
        async with asyncio.timeout(170):
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    async with app.state.database.begin() as conn:
                        result = await execute(
                            conn,
                            "UPDATE payment_orders SET "
                            "check_lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 SECOND) "
                            "WHERE id=:id AND check_lease_owner=:lease AND "
                            "check_lease_until>UTC_TIMESTAMP(6)",
                            id=row["id"],
                            lease=row["check_lease_owner"],
                        )
                    if not result.rowcount:
                        return False
                    if heartbeat:
                        heartbeat.write(healthy=True)
            await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return True
