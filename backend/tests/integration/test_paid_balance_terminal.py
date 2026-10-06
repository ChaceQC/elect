"""R2支付终态与旧调度修复，仅调用合成Room客户端。"""

from types import SimpleNamespace

import pytest
from query_resource_support import requires_mysql, run
from test_payment_polling import read, seed

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute
from services.payment.reconciliation import check_tick
from services.payment.repair_balance_refresh import repair_batch

pytestmark = requires_mysql


async def due(engine, order):
    async with engine.begin() as conn:
        await execute(conn, "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) WHERE id=:id",
                      id=order.bytes)


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_failed_balance_ends_tracking_and_paid_never_regresses(terminal):
    async def case(engine):
        order, _ = await seed(engine)
        calls, operation = [], new_id()

        async def call(service, path, *args, **kwargs):
            calls.append(path)
            if path == "/payments/check":
                return {"order_state": "paid_confirmed"}
            if path == "/controls/payment-balance-refresh":
                return {"operation_id": str(operation)}
            return {"state": terminal}

        app = SimpleNamespace(state=SimpleNamespace(
            database=engine, service_client=SimpleNamespace(call=call)))
        assert await check_tick(app, order_id=order)
        row = await read(engine, order)
        assert row["state"] == "paid_confirmed" and row["balance_refresh_state"] == "failed"
        assert row["next_check_at"] is None
        original_calls = list(calls)
        for _ in range(3):
            assert not await check_tick(app, order_id=order)
        assert calls == original_calls
    run("payment", case)


def test_temporary_503_preserves_operation_pending_and_30_second_backoff():
    async def case(engine):
        order, _ = await seed(engine)
        calls, operation = [], new_id()

        async def call(service, path, *args, **kwargs):
            calls.append(path)
            if path == "/payments/check":
                return {"order_state": "paid_confirmed"}
            if path == "/controls/payment-balance-refresh":
                return {"operation_id": str(operation)}
            if calls.count(path) == 1:
                raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic", True)
            return {"state": "succeeded"}

        app = SimpleNamespace(state=SimpleNamespace(
            database=engine, service_client=SimpleNamespace(call=call)))
        await check_tick(app, order_id=order)
        row = await read(engine, order)
        assert row["balance_refresh_operation_id"] == operation.bytes
        assert row["balance_refresh_state"] == "pending"
        assert (row["next_check_at"] - row["last_checked_at"]).total_seconds() == 30
        await due(engine, order)
        await check_tick(app, order_id=order)
        row = await read(engine, order)
        assert row["state"] == "paid_confirmed" and row["balance_refresh_state"] == "succeeded"
        assert row["next_check_at"] is None
        assert calls.count("/controls/payment-balance-refresh") == calls.count("/payments/check") == 1
    run("payment", case)


def test_legacy_repair_dry_run_apply_resume_and_unconfirmed():
    async def case(engine):
        results, orders = {}, []
        for result in ("failed", "running", "succeeded", "missing"):
            order, _ = await seed(engine)
            orders.append(order)
            operation = new_id()
            results[str(operation)] = result
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET state='paid_confirmed',"
                              "balance_refresh_state='failed',balance_refresh_operation_id=:op "
                              "WHERE id=:id", id=order.bytes, op=operation.bytes)

        async def call(service, path, scope, request, payload, **kwargs):
            assert path == "/browser/operation"
            result = results[payload["operation_id"]]
            if result == "missing":
                raise ApiError(404, ErrorCode.NOT_FOUND, "synthetic")
            return {"state": result}

        state = SimpleNamespace(database=engine, service_client=SimpleNamespace(call=call))
        before = [dict(await read(engine, order)) for order in orders]
        report = await repair_batch(state)
        assert report["counts"]["unconfirmed"] == 1
        assert [dict(await read(engine, order)) for order in orders] == before
        cursor = bytes(16)
        applied = 0
        while True:
            report = await repair_batch(state, apply=True, after=cursor, batch_size=2)
            applied += report["counts"].get("applied", 0)
            cursor = bytes.fromhex(report["after"])
            if report["exhausted"]:
                break
        assert applied == 3
        assert (await read(engine, orders[0]))["next_check_at"] is None
        assert (await read(engine, orders[1]))["balance_refresh_state"] == "pending"
        assert (await read(engine, orders[2]))["balance_refresh_state"] == "succeeded"
        assert dict(await read(engine, orders[3])) == before[3]
        assert (await repair_batch(state, apply=True))["counts"] == {
            "candidates": 1, "unconfirmed": 1,
        }
    run("payment", case)
