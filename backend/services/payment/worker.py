"""MySQL 扫描优先；重复唤醒或 Worker 重启不会重置学校 dispatch。"""

import asyncio
from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import DispatchOrder, PaymentSessionCommand
from services.common.security import Principal

from . import jobs
from .states import ORDER


async def advance(app, row):
    state = app.state
    if row["state"] in ORDER.terminal:
        await jobs.update(state.database, row, operation_state="cancelled")
        return
    owner, order = UUID(bytes=row["owner_user_id"]), UUID(bytes=row["id"])
    principal = Principal("payment", owner, 1, new_id())
    common = {
        "owner_user_id": owner,
        "request_id": principal.request_id,
        "order_id": order,
        "upstream_operation_id": UUID(bytes=row["upstream_operation_id"]),
        "operation_id": UUID(bytes=row["operation_id"]),
        "lease_owner": row["lease_owner"],
    }
    if row["kind"] == "create_order":
        command = DispatchOrder(
            **common,
            credential_ref=UUID(bytes=row["credential_ref"]),
            credential_version=row["credential_version"],
            binding_id=UUID(bytes=row["binding_id"]),
            amount=format(row["amount"], ".2f"),
            currency=row["currency"],
        )
        value = await state.service_client.call(
            "school_adapter",
            "/payments/dispatch",
            "school:payment",
            principal.request_id,
            command.model_dump(mode="json"),
            principal=principal,
        )
        if value["state"] != "confirmed":
            rejected = value["state"] == "rejected"
            unknown = value["state"] in {"unknown", "dispatched", "reconciling"}
            await jobs.update(
                state.database,
                row,
                order_state="rejected"
                if rejected
                else "submit_unknown"
                if unknown
                else "submitting",
                error=value["error_code"],
                operation_state="failed" if rejected else "unknown" if unknown else "reconciling",
                delay=300 if unknown else 30,
            )
            return
        if not await jobs.update(
            state.database,
            row,
            order_state="awaiting_payment" if row["state"] != "status_unknown" else None,
            qr_status="generating",
        ):
            return
    flow = PaymentSessionCommand(**common, step="E04" if row["kind"] == "qr_refresh" else "E01")
    value = await state.service_client.call(
        "school_adapter",
        "/payments/flow",
        "school:payment",
        principal.request_id,
        flow.model_dump(mode="json"),
        principal=principal,
    )
    status = value["qr_status"]
    await jobs.update(
        state.database,
        row,
        qr_status=status,
        qr_error=value["error_code"],
        operation_state={
            "ready": "succeeded",
            "failed": "failed",
            "unknown": "unknown",
            "generating": "reconciling",
        }[status],
        delay=300 if status == "unknown" else 30,
    )


async def execute(app, row, heartbeat=None):
    task = asyncio.create_task(advance(app, row))
    try:
        async with asyncio.timeout(170):
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done:
                    if not await jobs.renew(app.state.database, row):
                        return
                    if heartbeat:
                        heartbeat.write(healthy=True)
            await task
    except (ApiError, TimeoutError) as error:
        await jobs.update(
            app.state.database,
            row,
            error=getattr(error, "code", "DEPENDENCY_UNAVAILABLE"),
            operation_state="reconciling",
        )
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def worker_tick(app, heartbeat=None, order_id=None, *, stop=None):
    row = await jobs.claim(app.state.database, order_id)
    if row:
        await execute(app, row, heartbeat)
        return True
    from .reconciliation import check_tick

    if stop and stop.is_set():
        return False
    return await check_tick(app, heartbeat, order_id)
