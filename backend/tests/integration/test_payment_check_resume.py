"""原订单显式恢复的持久窗口、幂等、版本与本人权限。"""

import pytest
from query_resource_support import requires_mysql, run
from test_payment_polling import read, seed

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first
from services.payment import api, cancellation, check_resume, orders

pytestmark = requires_mysql


def test_created_deadline_is_fifteen_minutes_and_replay_never_renews_it():
    async def case(engine):
        principal = Principal("payment", new_id(), 1, new_id())
        command = api.CreateCommand(binding_id=new_id(), amount="1.00",
                                    idempotency_key=str(new_id()))
        binding = {"display_name": "合成寝室"}
        credential = {"credential_ref": str(new_id()), "credential_version": 1}
        accepted = await orders.create_order(engine, principal, command, binding, credential)
        before = await read(engine, accepted.order_id)
        assert (before["check_deadline_at"] - before["created_at"]).total_seconds() == 900
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET "
                          "check_deadline_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) "
                          "WHERE id=:id", id=accepted.order_id.bytes)
        expired = await read(engine, accepted.order_id)
        repeated = await orders.create_order(engine, principal, command, binding, credential)
        assert repeated.order_id == accepted.order_id
        assert (await read(engine, accepted.order_id))["check_deadline_at"] == expired[
            "check_deadline_at"]
        with pytest.raises(ApiError) as failure:
            await orders.create_order(engine, principal,
                command.model_copy(update={"idempotency_key": str(new_id())}), binding, credential)
        assert failure.value.status == 409

    run("payment", case)


def test_resume_uses_original_operations_and_never_extends_an_active_window():
    async def case(engine):
        order, owner = await seed(engine)
        principal = Principal("payment", owner, 1, new_id())
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET "
                          "created_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 16 MINUTE) "
                          "WHERE id=:id", id=order.bytes)
            operation = await first(conn, "SELECT * FROM payment_operations WHERE order_id=:id",
                                    id=order.bytes)
        before = await read(engine, order)
        for actor, version, status in [
            (Principal("payment", new_id(), 1, new_id()), 1, 404),
            (principal, None, 428), (principal, 2, 409),
        ]:
            with pytest.raises(ApiError) as failure:
                await check_resume.resume(engine, actor, order, version)
            assert failure.value.status == status
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET check_lease_owner='test',"
                          "check_lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 SECOND) "
                          "WHERE id=:id", id=order.bytes)
        with pytest.raises(ApiError) as failure:
            await check_resume.resume(engine, principal, order, 1)
        assert failure.value.status == 409
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET check_lease_owner=NULL,"
                          "check_lease_until=NULL WHERE id=:id", id=order.bytes)
        resumed = await check_resume.resume(engine, principal, order, 1)
        assert resumed.order_id == order and not resumed.check_paused and resumed.version == 2
        assert resumed.state == "awaiting_payment"
        repeated = await check_resume.resume(engine, principal, order, 1)
        assert repeated.check_deadline_at == resumed.check_deadline_at and repeated.version == 2
        after = await read(engine, order)
        for field in ("id", "created_at", "upstream_operation_id", "unresolved_binding_id",
                      "idempotency_key_hash", "request_digest"):
            assert after[field] == before[field]
        async with engine.connect() as conn:
            current = await first(conn, "SELECT *,UTC_TIMESTAMP(6) AS now FROM payment_operations "
                                  "WHERE order_id=:id", id=order.bytes)
            audits = await first(conn, "SELECT COUNT(*) AS n FROM outbox_events "
                                 "WHERE type='audit.recorded' AND "
                                 "JSON_UNQUOTE(JSON_EXTRACT(payload,'$.payload.action'))="
                                 "'payment.check_resumed'")
        assert current["id"] == operation["id"] and current["next_attempt_at"] is not None
        assert 890 < (after["check_deadline_at"] - current["now"]).total_seconds() <= 900
        assert after["next_check_at"] is not None and audits["n"] == 1
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET "
                          "check_deadline_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) "
                          "WHERE id=:id", id=order.bytes)
        with pytest.raises(ApiError) as failure:
            await check_resume.resume(engine, principal, order, 1)
        assert failure.value.status == 409
        cancelled = await cancellation.cancel(engine, principal, order, 2)
        with pytest.raises(ApiError) as failure:
            await check_resume.resume(engine, principal, order, cancelled.version)
        assert failure.value.status == 409

    run("payment", case)


def test_confirmed_payment_cannot_be_resumed_as_an_unpaid_order():
    async def case(engine):
        order, owner = await seed(engine)
        async with engine.begin() as conn:
            await execute(conn, "UPDATE payment_orders SET state='paid_confirmed',"
                          "balance_refresh_state='pending' WHERE id=:id", id=order.bytes)
        with pytest.raises(ApiError) as failure:
            await check_resume.resume(engine, Principal("payment", owner, 1, new_id()), order, 1)
        assert failure.value.status == 409
        assert (await read(engine, order))["state"] == "paid_confirmed"

    run("payment", case)
