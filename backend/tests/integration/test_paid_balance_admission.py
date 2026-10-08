"""付款后余额受理边界；真实Room/Payment事务，学校确认与故障仅为合成。"""

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from query_resource_support import counts, requires_mysql
from test_paid_balance_freshness import observed, scenario
from test_paid_balance_terminal import due
from test_payment_polling import read

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute
from services.payment.orders import order_view
from services.payment.reconciliation import check_tick
from services.room.balance import accept_refresh, claim_refresh, finish_refresh

pytestmark = requires_mysql


def restarted(context):
    return SimpleNamespace(state=SimpleNamespace(
        database=context.payment, service_client=context.payment_app.state.service_client))


async def complete_balance(context):
    claimed = await claim_refresh(context.room)
    assert claimed is not None
    value = observed(context, 1)
    assert await finish_refresh(
        context.room, claimed, value["items"], None, value["observation"])
    await due(context.payment, context.order)
    assert await check_tick(restarted(context), order_id=context.order)
    paid = await read(context.payment, context.order)
    assert paid["state"] == "paid_confirmed"
    assert paid["balance_refresh_state"] == "succeeded"
    assert paid["next_check_at"] is None


@pytest.mark.parametrize("binding_state", ["inactive", "missing"])
@pytest.mark.parametrize("legacy_pending", [False, True])
def test_invalid_binding_ends_unaccepted_refresh(binding_state, legacy_pending):
    async def case():
        async with scenario() as context:
            async with context.room.begin() as conn:
                if binding_state == "missing":
                    await execute(conn, "DELETE FROM room_bindings WHERE id=:id",
                                  id=context.binding.bytes)
                else:
                    await execute(conn, "UPDATE room_bindings SET status='inactive' WHERE id=:id",
                                  id=context.binding.bytes)
            if legacy_pending:
                async with context.payment.begin() as conn:
                    await execute(conn, "UPDATE payment_orders SET state='paid_confirmed',"
                                  "balance_refresh_state='pending',error_code='NOT_FOUND' "
                                  "WHERE id=:id", id=context.order.bytes)
            calls, original = [], context.payment_app.state.service_client.call

            async def call(service, path, *args, **kwargs):
                calls.append(path)
                return await original(service, path, *args, **kwargs)

            context.payment_app.state.service_client.call = call
            assert await check_tick(context.payment_app, order_id=context.order)
            paid = await read(context.payment, context.order)
            assert paid["state"] == "paid_confirmed"
            assert paid["balance_refresh_state"] == "failed"
            assert paid["balance_refresh_operation_id"] is None
            assert paid["error_code"] == "NOT_FOUND" and paid["next_check_at"] is None
            assert paid["check_lease_owner"] is None and paid["check_lease_until"] is None
            view = order_view(paid)
            assert view.paid_confirmed and view.balance_refresh_state == "failed"
            assert await counts(context.room, ["room_operations"]) == [0]
            assert calls.count("/payments/check") == (0 if legacy_pending else 1)
            assert calls.count("/controls/payment-balance-refresh") == 1
            assert "/browser/operation" not in calls
            original_calls = list(calls)
            await due(context.payment, context.order)  # 即使旧调度残留也不再领取失败记录。
            for _ in range(2):
                assert not await check_tick(restarted(context), order_id=context.order)
            assert calls == original_calls
    asyncio.run(case())


@pytest.mark.parametrize("status,code,retryable", [
    (429, ErrorCode.RATE_LIMITED, True),
    (503, ErrorCode.DEPENDENCY_UNAVAILABLE, True),
    (409, ErrorCode.OPERATION_IN_PROGRESS, False),
])
def test_temporary_admission_failure_retries_original_order(status, code, retryable):
    async def case():
        async with scenario() as context:
            attempts, original = [], context.payment_app.state.service_client.call

            async def call(service, path, scope, request_id, payload=None, **kwargs):
                if path == "/controls/payment-balance-refresh":
                    attempts.append(payload)
                    if len(attempts) == 1:
                        raise ApiError(status, code, "synthetic", retryable)
                return await original(service, path, scope, request_id, payload, **kwargs)

            context.payment_app.state.service_client.call = call
            assert await check_tick(context.payment_app, order_id=context.order)
            paid = await read(context.payment, context.order)
            assert paid["state"] == "paid_confirmed"
            assert paid["balance_refresh_state"] == "pending"
            assert paid["balance_refresh_operation_id"] is None and paid["error_code"] == code
            assert (paid["next_check_at"] - paid["last_checked_at"]).total_seconds() == 30
            await due(context.payment, context.order)
            assert await check_tick(restarted(context), order_id=context.order)
            assert attempts[0] == attempts[1]
            assert await counts(context.room, ["room_operations"]) == [1]
            await complete_balance(context)
            assert len(attempts) == 2
    asyncio.run(case())


@pytest.mark.parametrize("previously_linked", [False, True])
def test_operation_lookup_404_keeps_accepted_refresh(previously_linked):
    async def case():
        async with scenario() as context:
            operation = None
            if previously_linked:
                operation = await accept_refresh(
                    context.room, context.owner, context.binding,
                    f"payment-paid:{context.order}", source="payment")
                async with context.payment.begin() as conn:
                    await execute(conn, "UPDATE payment_orders SET state='paid_confirmed',"
                                  "balance_refresh_state='pending',"
                                  "balance_refresh_operation_id=:op "
                                  "WHERE id=:id", op=operation.bytes, id=context.order.bytes)
            calls, original = [], context.payment_app.state.service_client.call

            async def call(service, path, *args, **kwargs):
                calls.append(path)
                if path == "/browser/operation" and calls.count(path) == 1:
                    raise ApiError(404, ErrorCode.NOT_FOUND, "synthetic")
                return await original(service, path, *args, **kwargs)

            context.payment_app.state.service_client.call = call
            assert await check_tick(context.payment_app, order_id=context.order)
            paid = await read(context.payment, context.order)
            linked = UUID(bytes=paid["balance_refresh_operation_id"])
            assert operation is None or linked == operation
            assert paid["state"] == "paid_confirmed"
            assert paid["balance_refresh_state"] == "pending" and paid["error_code"] == "NOT_FOUND"
            assert (paid["next_check_at"] - paid["last_checked_at"]).total_seconds() == 30
            await complete_balance(context)
            assert (await read(context.payment, context.order))["balance_refresh_operation_id"] == (
                linked.bytes)
            admissions = calls.count("/controls/payment-balance-refresh")
            assert admissions == (0 if previously_linked else 1)
            assert await counts(context.room, ["room_operations"]) == [1]
    asyncio.run(case())
