"""只接受 Adapter 已验收映射；付款后重新查询学校余额，不做本地加法。"""

import asyncio
from contextlib import nullcontext
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.read_schedule import ReadSchedule, processing
from services.common.security import Principal
from services.common.sql import execute, first

from .check_claims import claim
from .check_window import deadline_sql
from .states import ORDER


async def balance_refresh(state, row, principal):
    operation = row["balance_refresh_operation_id"]
    try:
        if not operation:
            value = await state.service_client.call(
                "room", "/controls/payment-balance-refresh", "room:browser", principal.request_id,
                {"binding_id": str(UUID(bytes=row["binding_id"])),
                 "order_id": str(UUID(bytes=row["id"]))},
                principal=principal,
            )
            operation = UUID(value["operation_id"]).bytes
        result = await refresh_status(state, operation, principal)
        return operation, result, None
    except ApiError as failure:
        # Room受理前明确拒绝无效绑定；付款事实保留，余额跟踪按业务失败终结。
        if not operation and failure.status == 404 and failure.code == ErrorCode.NOT_FOUND:
            return None, "failed", failure.code
        # 接受成功后读取失败也保留operation，不能丢掉关联或误写业务failed。
        return operation, "unavailable", failure.code


async def refresh_status(state, operation, principal):
    if not operation:
        raise ApiError(404, ErrorCode.NOT_FOUND, "余额刷新关联缺失")
    value = await state.service_client.call(
        "room",
        "/browser/operation",
        "room:browser",
        principal.request_id,
        {"operation_id": str(UUID(bytes=operation))},
        principal=principal,
    )
    if value["state"] in {"failed", "cancelled"}:
        return "failed"
    if value["state"] == "succeeded":
        return "succeeded"
    if value["state"] in {"accepted", "running", "reconciling"}:
        return "pending"
    raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "余额刷新状态暂不可确认", True)


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
        if next_state == "paid_confirmed" and refresh_state == "pending":
            operation, refresh_state, error = await balance_refresh(state, row, principal)
            if refresh_state == "unavailable":
                refresh_state = "pending"
    except ApiError as failure:
        error = failure.code
        if next_state == "paid_confirmed":
            refresh_state = "pending"
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
            "next_check_at=IF(:finished OR "
            "(:state!='paid_confirmed' AND (cancel_requested_at IS NOT NULL OR "
            f"{deadline_sql()}<=UTC_TIMESTAMP(6))),"
            "NULL,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL :delay SECOND)),"
            "check_lease_owner=NULL,check_lease_until=NULL,balance_refresh_state=:refresh,"
            "balance_refresh_operation_id=:operation,version=version+1 WHERE id=:id",
            id=row["id"],
            state=next_state,
            error=error,
            refresh=refresh_state,
            operation=operation,
            finished=next_state in ORDER.terminal and (
                next_state != "paid_confirmed" or refresh_state != "pending"
            ),
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


async def check_tick(app, heartbeat=None, order_id=None, *, stop=None):
    if stop and stop.is_set():
        return False
    if not hasattr(app.state, "check_schedule"):
        app.state.check_schedule = ReadSchedule(("reconciliation",))
    row = await claim(app.state.database, order_id, app.state.check_schedule, stop=stop)
    if not row:
        return False
    with (heartbeat.work(170, lease_seconds=90) if heartbeat else nullcontext()) as work_health:
        with processing("payment", "reconciliation"):
            return await _check_claimed(app, row, work_health)


async def _check_claimed(app, row, work_health):
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
                    if work_health:
                        work_health.renew(90)
            await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return True
