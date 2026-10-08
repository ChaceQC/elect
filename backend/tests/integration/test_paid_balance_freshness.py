"""付款确认后的独立B02；真实Room/Payment事务，学校响应仅为合成。"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from query_resource_support import database, requires_mysql, seed_binding
from test_paid_balance_terminal import due
from test_payment_polling import read, seed

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import PaymentBalanceRefresh
from services.common.security import Principal
from services.common.sql import execute, first
from services.payment.reconciliation import check_tick
from services.room.balance import accept_refresh, claim_refresh, finish_refresh, get_balance
from services.room.balance_store import settle_aliases
from services.room.query_api import payment_refresh
from services.room.query_worker import refresh_tick
from services.room.repository import RoomRepository

pytestmark = requires_mysql


@asynccontextmanager
async def scenario():
    async with database("payment", production_pool=True) as payment, database(
        "room", production_pool=True
    ) as room:
        order, owner = await seed(payment)
        binding = UUID(bytes=(await read(payment, order))["binding_id"])
        await seed_binding(room, owner, binding)
        async with room.connect() as conn:
            target = await first(conn, "SELECT r.school_room_id FROM rooms r "
                                 "JOIN room_bindings b ON b.room_id=r.id WHERE b.id=:id",
                                 id=binding.bytes)
        app = SimpleNamespace(state=SimpleNamespace(database=room))
        context = SimpleNamespace(
            room=room, payment=payment, order=order, owner=owner, binding=binding,
            room_app=app, school_room=target["school_room_id"],
        )

        async def call(service, path, scope, request_id, payload=None, **kwargs):
            if path == "/payments/check":
                assert service == "school_adapter"
                return {"order_state": "paid_confirmed"}
            assert service == "room"
            if path == "/controls/payment-balance-refresh":
                return await payment_refresh(
                    PaymentBalanceRefresh(**payload), SimpleNamespace(app=app), kwargs["principal"]
                )
            assert path == "/browser/operation"
            return await RoomRepository(room).operation(owner, UUID(payload["operation_id"]))

        context.payment_app = SimpleNamespace(state=SimpleNamespace(
            database=payment, service_client=SimpleNamespace(call=call)))
        yield context


async def operation(context, identifier):
    async with context.room.connect() as conn:
        return await first(conn, "SELECT * FROM room_operations WHERE id=:id", id=identifier)


def observed(context, sequence):
    return {"items": [{"room_id": context.school_room, "balance": f"{9 + sequence}.00"}],
            "observation": {"sequence": sequence, "observed_at": datetime.now(UTC),
                            "request_id": new_id(), "source": "school_bound_rooms",
                            "error_code": None}}


@pytest.mark.parametrize("prior_source", ["browser", "payment"])
@pytest.mark.parametrize("new_read_fails", [False, True])
def test_prepaid_response_cannot_complete_payment_refresh(prior_source, new_read_fails):
    async def case():
        async with scenario() as context:
            old = await accept_refresh(context.room, context.owner, context.binding,
                                       str(new_id()), source=prior_source)
            captured, release = asyncio.Event(), asyncio.Event()
            reads = []

            async def school_call(service, path, *args, **kwargs):
                assert (service, path) == ("school_adapter", "/rooms/bound")
                reads.append(path)
                result = observed(context, len(reads))
                if len(reads) == 1:
                    captured.set()  # 已取得付款前余额，尚未交给Room提交。
                    await release.wait()
                elif new_read_fails:
                    raise ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "synthetic", True)
                return result

            context.room_app.state.service_client = SimpleNamespace(call=school_call)
            task = asyncio.create_task(refresh_tick(context.room_app))
            try:
                await asyncio.wait_for(captured.wait(), 5)
                assert await check_tick(context.payment_app, order_id=context.order)
                paid = await read(context.payment, context.order)
                fresh = paid["balance_refresh_operation_id"]
                assert fresh != old.bytes
                assert paid["state"] == "paid_confirmed"
                assert paid["balance_refresh_state"] == "pending"
                assert await claim_refresh(context.room) is None  # 原账号读取仍占租约。
                release.set()
                assert await task
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)

            await due(context.payment, context.order)
            await check_tick(context.payment_app, order_id=context.order)
            paid = await read(context.payment, context.order)
            assert paid["balance_refresh_state"] == "pending"
            assert (await operation(context, fresh))["saga_step"] == "read_school"
            balance = await get_balance(context.room, context.owner, context.binding)
            assert balance.amount == "10.00"
            assert await refresh_tick(context.room_app)
            await due(context.payment, context.order)
            await check_tick(context.payment_app, order_id=context.order)
            paid = await read(context.payment, context.order)
            assert paid["state"] == "paid_confirmed"
            assert paid["balance_refresh_state"] == ("failed" if new_read_fails else "succeeded")
            assert paid["next_check_at"] is None
            assert len(reads) == 2
            balance = await get_balance(context.room, context.owner, context.binding)
            assert balance.amount == ("10.00" if new_read_fails else "11.00")
    asyncio.run(case())


def test_queued_reads_and_other_payments_do_not_absorb_new_order():
    async def case():
        async with scenario() as context:
            old = await accept_refresh(context.room, context.owner, context.binding, str(new_id()))
            await check_tick(context.payment_app, order_id=context.order)
            fresh = (await read(context.payment, context.order))["balance_refresh_operation_id"]
            second = await accept_refresh(context.room, context.owner, context.binding,
                                          f"payment-paid:{new_id()}", source="payment")
            for identifier in (old.bytes, fresh, second.bytes):
                row = await operation(context, identifier)
                assert row["saga_step"] == "read_school"
                assert row["upstream_operation_id"] is None
            # 浏览器继续复用已有任务；支付的独立任务不改变普通查询合并。
            browser = await accept_refresh(context.room, context.owner, context.binding,
                                           str(new_id()))
            assert (await operation(context, browser.bytes))["upstream_operation_id"] == old.bytes
    asyncio.run(case())


def test_lost_acceptance_response_concurrent_replay_and_worker_recreation():
    async def case():
        async with scenario() as context:
            request = SimpleNamespace(app=context.room_app)
            command = PaymentBalanceRefresh(binding_id=context.binding, order_id=context.order)
            principal = Principal("payment", context.owner, 1, new_id())
            results = await asyncio.gather(*[
                payment_refresh(command, request, principal) for _ in range(5)
            ])
            identifier = UUID(results[0]["operation_id"])
            assert all(item["operation_id"] == str(identifier) for item in results)
            # Room受理响应丢失，Payment未记operation；重建Worker后从订单固定键恢复。
            paid = await read(context.payment, context.order)
            assert paid["balance_refresh_operation_id"] is None
            await check_tick(context.payment_app, order_id=context.order)
            assert (await read(context.payment, context.order))[
                "balance_refresh_operation_id"] == identifier.bytes
            reads = []

            async def school_call(*args, **kwargs):
                reads.append(True)
                return observed(context, 2)

            worker = SimpleNamespace(state=SimpleNamespace(
                database=context.room, service_client=SimpleNamespace(call=school_call)))
            assert await refresh_tick(worker)
            assert not await refresh_tick(worker)
            assert (await payment_refresh(command, request, principal))["state"] == "succeeded"
            assert len(reads) == 1
            async with context.room.connect() as conn:
                assert (await first(conn, "SELECT COUNT(*) AS n FROM room_operations"))["n"] == 1
    asyncio.run(case())


@pytest.mark.parametrize("root_already_complete", [False, True])
def test_legacy_pending_payment_alias_is_read_independently(root_already_complete):
    async def case():
        async with scenario() as context:
            old = await accept_refresh(context.room, context.owner, context.binding, str(new_id()))
            claimed = await claim_refresh(context.room)
            await check_tick(context.payment_app, order_id=context.order)
            fresh = (await read(context.payment, context.order))["balance_refresh_operation_id"]
            value = observed(context, 1)

            async def complete_old():
                assert await finish_refresh(context.room, claimed, value["items"], None,
                                            value["observation"])

            if root_already_complete:
                await complete_old()
            # 模拟旧版持久别名，覆盖旧根已提交、别名尚未分批传播的恢复场景。
            async with context.room.begin() as conn:
                await execute(conn, "UPDATE room_operations SET saga_step='merged',"
                              "upstream_operation_id=:old WHERE id=:id", old=old.bytes, id=fresh)
            if not root_already_complete:
                await complete_old()
            assert not await settle_aliases(context.room)
            assert (await operation(context, fresh))["state"] == "accepted"

            async def school_call(*args, **kwargs):
                return observed(context, 2)

            context.room_app.state.service_client = SimpleNamespace(call=school_call)
            assert await refresh_tick(context.room_app)
            updated = await operation(context, fresh)
            assert updated["state"] == "succeeded"
            assert updated["upstream_operation_id"] is None
            await due(context.payment, context.order)
            await check_tick(context.payment_app, order_id=context.order)
            paid = await read(context.payment, context.order)
            assert paid["balance_refresh_state"] == "succeeded"
            balance = await get_balance(context.room, context.owner, context.binding)
            assert balance.amount == "11.00"
    asyncio.run(case())
