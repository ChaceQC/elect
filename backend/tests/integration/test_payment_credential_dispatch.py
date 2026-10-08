"""问题3：未发送凭据拒绝终结，已发送结果未知保持占位。"""

import asyncio

import pytest
from payment_dispatch_support import PAYLOAD, run
from query_resource_support import counts, requires_mysql

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute
from services.payment import jobs, reconciliation, worker
from services.school_adapter.application.payment_orders import SchoolOrders

pytestmark = requires_mysql


@pytest.mark.parametrize("legacy", [False, True])
def test_queued_reauthentication_rejects_releases_slot_and_replays(legacy, monkeypatch):
    async def case(s):
        await s.reauthenticate()
        if legacy:
            async with s.payment.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET state='submit_unknown',"
                              "error_code='NOT_FOUND' WHERE id=:id", id=s.order.bytes)
                await execute(conn, "UPDATE payment_operations SET state='reconciling',"
                              "error_code='SCHOOL_REAUTH_REQUIRED' WHERE order_id=:id",
                              id=s.order.bytes)
        assert await worker.worker_tick(s.app, order_id=s.order)
        row, operation = await s.read(), await s.operation()
        assert row["state"] == "rejected" and row["error_code"] == ErrorCode.SCHOOL_REAUTH_REQUIRED
        assert row["unresolved_binding_id"] is None and row["cancelled_at"] is None
        assert operation["state"] == "failed" and operation["lease_owner"] is None
        ledger = await s.school.ledger.get(s.owner, s.order)
        assert ledger["state"] == "rejected" and ledger["dispatched_at"] is None
        assert s.posts == s.flows == 0
        assert not await jobs.claim(s.payment, s.order)
        assert not await reconciliation.claim(s.payment, s.order)
        assert (await s.create(version=2)).order_id == s.order  # 原键保持原终态。
        new_command = s.command.model_copy(update={"idempotency_key": str(new_id())})
        assert (await s.create(version=2, command=new_command)).order_id != s.order
    run(case, monkeypatch)


@pytest.mark.parametrize("invalid", ["missing", "revoked", "forbidden", "reference"])
def test_invalid_credential_before_ledger_is_never_dispatched(invalid, monkeypatch):
    async def case(s):
        async with s.adapter.begin() as conn:
            if invalid == "missing":
                await execute(conn, "DELETE FROM school_credentials")
            elif invalid == "revoked":
                await execute(conn, "UPDATE school_credentials SET status='revoked'")
            elif invalid == "forbidden":
                await execute(conn, "UPDATE school_credentials SET use_allowed=0")
            else:
                await execute(conn, "UPDATE school_credentials SET id=:id", id=new_id().bytes)
        await worker.worker_tick(s.app, order_id=s.order)
        assert (await s.read())["state"] == "rejected"
        assert (await s.operation())["state"] == "failed"
        assert s.posts == s.flows == 0
    run(case, monkeypatch)


@pytest.mark.parametrize("dispatched", [False, True])
def test_reauthentication_after_prepare_preserves_dispatch_boundary(dispatched, monkeypatch):
    async def case(s):
        row, command = await s.claim()
        await s.school.ledger.prepare(command, PAYLOAD)
        if dispatched:
            assert await s.school.ledger.reserve(command, s.principal)
        await s.reauthenticate()
        # 模拟另一个执行者已经持有prepared快照；终结必须锁内重查发送状态。
        latest = await s.school.ledger.get(s.owner, s.order)
        await s.school.send(command, s.principal, {**latest, "state": "prepared"})
        await worker.execute(s.app, row)
        result, operation = await s.read(), await s.operation()
        ledger = await s.school.ledger.get(s.owner, s.order)
        assert result["state"] == ("submit_unknown" if dispatched else "rejected")
        assert operation["state"] == ("unknown" if dispatched else "failed")
        assert ledger["state"] == ("unknown" if dispatched else "rejected")
        assert bool(ledger["dispatched_at"]) is dispatched
        assert bool(result["unresolved_binding_id"]) is dispatched
        assert s.posts == s.flows == 0
    run(case, monkeypatch)


@pytest.mark.parametrize("state", ["confirmed", "unknown", "rejected"])
def test_existing_ledger_is_authoritative_after_reauthentication(state, monkeypatch):
    async def case(s):
        _, command = await s.claim()
        await s.school.ledger.prepare(command, PAYLOAD)
        async with s.adapter.begin() as conn:
            await execute(conn, "UPDATE upstream_operations SET state=:state,"
                          "dispatched_at=UTC_TIMESTAMP(6) WHERE id=:id",
                          state=state, id=command.upstream_operation_id.bytes)
        before = dict(await s.school.ledger.get(s.owner, s.order))
        await s.reauthenticate()
        await s.school.ledger.prepare(command, PAYLOAD)
        assert dict(await s.school.ledger.get(s.owner, s.order)) == before
        for change in ({"amount": "2.00"}, {"owner_user_id": new_id()}):
            with pytest.raises(ApiError) as failure:
                await s.school.ledger.prepare(command.model_copy(update=change), PAYLOAD)
            assert failure.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
        assert dict(await s.school.ledger.get(s.owner, s.order)) == before
        assert s.posts == 0
    run(case, monkeypatch)


def test_rejected_response_loss_resumes_from_durable_ledger(monkeypatch):
    async def case(s):
        await s.reauthenticate()

        async def lose_response(*args, **kwargs):
            result = await s.call(*args, **kwargs)
            if args[1] == "/payments/dispatch":
                assert result["state"] == "rejected"
                raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic", True)
            return result

        s.app.state.service_client.call = lose_response
        await worker.worker_tick(s.app, order_id=s.order)
        assert (await s.read())["state"] == "submitting"
        assert (await s.operation())["state"] == "reconciling"
        s.school = SchoolOrders(s.school.state)  # 重建执行器，不依赖内存拒绝标记。
        s.app.state.service_client.call = s.call
        async with s.payment.begin() as conn:
            await execute(conn, "UPDATE payment_operations SET next_attempt_at=UTC_TIMESTAMP(6)")
        await worker.worker_tick(s.app, order_id=s.order)
        assert (await s.read())["state"] == "rejected"
        assert (await s.operation())["state"] == "failed"
        assert s.posts == s.flows == 0
    run(case, monkeypatch)


def test_dependency_error_does_not_claim_unsent_rejection_and_can_recover(monkeypatch):
    async def case(s):
        original = s.school.ledger.credential

        async def unavailable(*args):
            raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic", True)

        monkeypatch.setattr(s.school.ledger, "credential", unavailable)
        await worker.worker_tick(s.app, order_id=s.order)
        assert (await s.operation())["state"] == "reconciling"
        assert (await s.read())["unresolved_binding_id"] == s.binding.bytes
        assert await counts(s.adapter, ["upstream_operations", "adapter_payment_orders"]) == [0, 0]
        monkeypatch.setattr(s.school.ledger, "credential", original)
        async with s.payment.begin() as conn:
            await execute(conn, "UPDATE payment_operations SET next_attempt_at=UTC_TIMESTAMP(6)")
        await worker.worker_tick(s.app, order_id=s.order)
        assert (await s.read())["state"] == "awaiting_payment"
        assert (await s.operation())["state"] == "succeeded"
        assert s.posts == s.flows == 1
    run(case, monkeypatch)


def test_rejection_is_atomic_and_duplicate_prepare_is_idempotent(monkeypatch):
    async def case(s):
        _, command = await s.claim()
        await s.reauthenticate()
        original = s.school.ledger.crypto.seal

        def fail(*args):
            raise RuntimeError("synthetic rollback")

        monkeypatch.setattr(s.school.ledger.crypto, "seal", fail)
        with pytest.raises(RuntimeError, match="synthetic rollback"):
            await s.school.ledger.prepare(command, PAYLOAD)
        assert await counts(s.adapter, ["upstream_operations", "adapter_payment_orders"]) == [0, 0]
        monkeypatch.setattr(s.school.ledger.crypto, "seal", original)
        await asyncio.gather(*(s.school.ledger.prepare(command, PAYLOAD) for _ in range(2)))
        assert await counts(s.adapter, ["upstream_operations", "adapter_payment_orders"]) == [1, 1]
        row = await s.school.ledger.get(s.owner, s.order)
        assert row["state"] == "rejected" and row["dispatched_at"] is None
        assert s.posts == 0
    run(case, monkeypatch)


@pytest.mark.parametrize("error", [ErrorCode.SCHOOL_REAUTH_REQUIRED, ErrorCode.SCHOOL_TIMEOUT])
def test_error_after_school_dispatch_is_unknown_and_never_resent(error, monkeypatch):
    async def case(s):
        s.after_error = ApiError(409 if error == ErrorCode.SCHOOL_REAUTH_REQUIRED else 504,
                                 error, "synthetic", True)
        await worker.worker_tick(s.app, order_id=s.order)
        assert (await s.read())["state"] == "submit_unknown"
        assert (await s.read())["unresolved_binding_id"] == s.binding.bytes
        assert (await s.school.ledger.get(s.owner, s.order))["dispatched_at"]
        await s.reauthenticate()
        async with s.payment.begin() as conn:
            await execute(conn, "UPDATE payment_operations SET next_attempt_at=UTC_TIMESTAMP(6)")
        await worker.worker_tick(s.app, order_id=s.order)
        assert (await s.read())["state"] == "submit_unknown"
        assert s.posts == 1 and s.flows == 0
        with pytest.raises(ApiError) as failure:
            await s.create(version=2, command=s.command.model_copy(
                update={"idempotency_key": str(new_id())}))
        assert failure.value.code == ErrorCode.OPERATION_IN_PROGRESS
    run(case, monkeypatch)
