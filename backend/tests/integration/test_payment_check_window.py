"""订单期限、旧库升级及在途结果；一次性MySQL，学校/Room完全合成。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from query_resource_support import database, migrate, requires_mysql, run
from test_payment_polling import read, seed

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first
from services.payment import api, jobs, orders, qr, reconciliation, worker

pytestmark = requires_mysql


def app_for(engine, call):
    return SimpleNamespace(state=SimpleNamespace(
        database=engine, service_client=SimpleNamespace(call=call),
    ))


async def expire(engine, order):
    async with engine.begin() as conn:
        await execute(conn, "UPDATE payment_orders SET "
                      "check_deadline_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) "
                      "WHERE id=:id", id=order.bytes)


@pytest.mark.parametrize("state", ["awaiting_payment", "submit_unknown"])
def test_legacy_order_upgrade_stops_both_roles_without_changing_result(state):
    async def case():
        async with database("payment", revision="payment_0006") as engine:
            order, owner = await seed(engine)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET state=:state,"
                              "created_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 16 MINUTE) "
                              "WHERE id=:id", state=state, id=order.bytes)
                await execute(conn, "UPDATE payment_operations SET state='unknown' "
                              "WHERE order_id=:id", id=order.bytes)
                await conn.run_sync(migrate, "payment")
                await conn.run_sync(migrate, "payment")
            original = await read(engine, order)
            assert original["check_deadline_at"] is None
            call = AsyncMock(side_effect=AssertionError("超时任务不得调用学校"))
            app = app_for(engine, call)
            assert not await worker.worker_tick(app, order_id=order)
            assert not await reconciliation.check_tick(app, order_id=order)
            await jobs.recover(engine)
            assert not await worker.worker_tick(app, order_id=order)
            row = await read(engine, order)
            assert row["state"] == state and row["next_check_at"] is None
            assert row["last_checked_at"] is None and row["cancelled_at"] is None
            for field in ("id", "upstream_operation_id", "idempotency_key_hash",
                          "created_at", "unresolved_binding_id"):
                assert row[field] == original[field]
            principal = Principal("payment", owner, 1, new_id())
            for _ in range(2):
                view = await api.read_order(SimpleNamespace(order_id=order),
                                            SimpleNamespace(app=app), principal)
                assert view.check_paused and view.state == state
            assert (await read(engine, order))["next_check_at"] is None
            async with engine.connect() as conn:
                operation = await first(conn, "SELECT * FROM payment_operations WHERE order_id=:id",
                                        id=order.bytes)
            assert operation["state"] == "unknown" and operation["next_attempt_at"] is None
            call.assert_not_awaited()

    asyncio.run(case())


@pytest.mark.parametrize("paid", [False, True])
def test_expiry_drains_check_and_qr_preserving_paid_evidence(paid):
    async def case(engine):
        order, owner = await seed(engine)
        entered, release = asyncio.Event(), asyncio.Event()
        calls, balance_done = [], False
        balance_id = new_id()

        async def call(service, path, *args, **kwargs):
            calls.append(path)
            if path == "/payments/check":
                entered.set()
                await release.wait()
                return {"order_state": "paid_confirmed" if paid else "status_unknown"}
            if path == "/controls/payment-balance-refresh":
                return {"operation_id": str(balance_id)}
            return {"state": "succeeded" if balance_done else "running"}

        app = app_for(engine, call)
        claimed = await jobs.claim(engine, order)
        async with asyncio.timeout(8):
            task = asyncio.create_task(reconciliation.check_tick(app, order_id=order))
            await entered.wait()
            await expire(engine, order)
            assert not orders.order_view(await orders.get_order(engine, owner, order)).check_paused
            assert await jobs.update(engine, claimed, qr_status="ready",
                                     operation_state="succeeded")
            assert (await read(engine, order))["next_check_at"] is None
            assert not orders.order_view(await orders.get_order(engine, owner, order)).check_paused
            release.set()
            assert await task
        row = await read(engine, order)
        assert row["last_checked_at"] and row["qr_status"] == "ready"
        view = orders.order_view(await orders.get_order(engine, owner, order))
        if not paid:
            assert view.check_paused and row["state"] == "status_unknown"
            assert row["next_check_at"] is None
            assert not await reconciliation.check_tick(app, order_id=order)
        else:
            assert not view.check_paused and view.paid_confirmed
            assert row["balance_refresh_state"] == "pending" and row["next_check_at"]
            balance_done = True
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) "
                              "WHERE id=:id", id=order.bytes)
            assert await reconciliation.check_tick(app, order_id=order)
            row = await read(engine, order)
            assert row["balance_refresh_state"] == "succeeded" and row["next_check_at"] is None
            assert calls.count("/controls/payment-balance-refresh") == 1
        assert calls.count("/payments/check") == 1

    run("payment", case)


def test_expired_interrupted_worker_does_not_restart_after_recovery():
    async def case(engine):
        order, owner = await seed(engine)
        await expire(engine, order)
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET state='submitting' WHERE id=:id",
                          id=order.bytes)
            await execute(conn, "UPDATE payment_operations SET state='running',lease_owner='test',"
                          "lease_until=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) "
                          "WHERE order_id=:id", id=order.bytes)
        assert await jobs.recover(engine)
        async with engine.connect() as conn:
            operation = await first(conn, "SELECT * FROM payment_operations WHERE order_id=:id",
                                    id=order.bytes)
        assert operation["state"] == "reconciling" and operation["next_attempt_at"] is None
        call = AsyncMock(side_effect=AssertionError("恢复器不得重新启动过期任务"))
        app = app_for(engine, call)
        assert not await worker.worker_tick(app, order_id=order)
        assert not await reconciliation.check_tick(app, order_id=order)
        view = orders.order_view(await orders.get_order(engine, owner, order))
        assert view.check_paused and view.state == "submit_unknown"
        call.assert_not_awaited()

    run("payment", case)


def test_qr_replay_and_new_key_cannot_extend_expired_order():
    async def case(engine):
        order, owner = await seed(engine)
        original = await qr.refresh(engine, owner, order, "original-qr-request-key")
        await expire(engine, order)
        before = await read(engine, order)
        repeated = await qr.refresh(engine, owner, order, "original-qr-request-key")
        assert repeated.operation_id == original.operation_id
        with pytest.raises(ApiError) as failure:
            await qr.refresh(engine, owner, order, "different-qr-request-key")
        assert failure.value.status == 409
        after = await read(engine, order)
        assert after["check_deadline_at"] == before["check_deadline_at"]
        assert orders.order_view(await orders.get_order(engine, owner, order)).check_paused

    run("payment", case)


def test_active_failure_backs_off_but_expiry_stops_further_queries():
    async def case(engine):
        order, _ = await seed(engine)
        call = AsyncMock(side_effect=ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "合成故障"))
        app = app_for(engine, call)
        assert await reconciliation.check_tick(app, order_id=order)
        row = await read(engine, order)
        assert (row["next_check_at"] - row["last_checked_at"]).total_seconds() == 30
        await expire(engine, order)
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) "
                          "WHERE id=:id", id=order.bytes)
        assert not await reconciliation.check_tick(app, order_id=order)
        assert (await read(engine, order))["next_check_at"] is None
        call.assert_awaited_once()

    run("payment", case)
