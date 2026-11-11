"""R5真实MySQL领取互斥、锁跳过、取消、接管及停止栅栏。"""

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from query_resource_support import database, requires_mysql, seed_binding
from test_history_admission import accept, request
from test_payment_polling import read, seed

from services.common.ids import new_id
from services.common.read_schedule import ReadSchedule
from services.common.security import Principal
from services.common.sql import execute
from services.payment import cancellation, check_claims, reconciliation
from services.room import balance, history_jobs, read_claims
from services.room.history_store import finish_history
from services.room.repository import RoomRepository

pytestmark = requires_mysql
KINDS = ("binding_sync", "balance_refresh", "history_sync")


async def room_jobs(engine, owner=None):
    owner, binding = owner or new_id(), new_id()
    await seed_binding(engine, owner, binding)
    await accept(engine, owner, binding, request(1, 14))
    await balance.accept_refresh(engine, owner, binding, str(new_id()))
    await RoomRepository(engine).accept_sync(owner, str(new_id()))
    return owner, binding


def test_room_class_exclusion_lock_skip_and_old_epoch(monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")

    async def case():
        async with database("room", production_pool=True) as engine:
            owner, _ = await room_jobs(engine, UUID(int=1))
            other, _ = await room_jobs(engine, UUID(int=2))
            schedule = ReadSchedule(KINDS)
            async with engine.begin() as blocker:
                await execute(blocker, "SELECT owner_user_id FROM room_preferences "
                              "WHERE owner_user_id=:owner FOR UPDATE", owner=owner.bytes)
                async with asyncio.timeout(1):
                    free = await history_jobs.claim_history(engine, schedule)
                assert free["owner_user_id"] == other.bytes
            first = await history_jobs.claim_history(engine, schedule)
            assert first["owner_user_id"] == owner.bytes
            # 两个owner的历史租约不阻止各自领取一个B02。
            balances = [await balance.claim_refresh(engine, schedule) for _ in range(2)]
            assert {row["owner_user_id"] for row in balances} == {owner.bytes, other.bytes}
            assert not await RoomRepository(engine).claim(schedule)
            assert not await history_jobs.claim_history(engine, schedule)

            # 模拟候选查询后另一领取已提交，锁内仍须按同类租约复核。
            original = read_claims.candidates

            async def stale_candidates(*args):
                return [owner.bytes]

            monkeypatch.setattr(read_claims, "candidates", stale_candidates)
            assert not await RoomRepository(engine).claim(schedule)
            assert not await history_jobs.claim_history(engine, schedule)
            monkeypatch.setattr(read_claims, "candidates", original)

            async with engine.begin() as conn:
                await execute(conn, "UPDATE history_sync_windows SET lease_until="
                              "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE id=:id",
                              id=first["id"])
            newer = await history_jobs.claim_history(engine, schedule)
            assert newer["execution_epoch"] == first["execution_epoch"] + 1
            empty = {"items": [], "request_room_id": "synthetic"}
            assert not await finish_history(engine, first, empty, None, False)
            assert await finish_history(engine, newer, empty, None, False)
            picked = await history_jobs.claim_history(engine, schedule)
            assert picked["owner_user_id"] == owner.bytes
            assert picked["id"] != first["id"]
    asyncio.run(case())


@pytest.mark.parametrize("legacy_alias", [False, True])
def test_payment_balance_waits_for_b02_but_not_history(legacy_alias):
    async def case():
        async with database("room") as engine:
            owner, binding = new_id(), new_id()
            await seed_binding(engine, owner, binding)
            await accept(engine, owner, binding)
            browser = await balance.accept_refresh(engine, owner, binding, str(new_id()))
            payment = await balance.accept_refresh(
                engine, owner, binding, str(new_id()), source="payment")
            repository = RoomRepository(engine)
            await repository.accept_sync(owner, str(new_id()))
            if legacy_alias:
                async with engine.begin() as conn:
                    await execute(conn, "UPDATE room_operations SET saga_step='merged',"
                                  "upstream_operation_id=:root WHERE id=:id",
                                  root=browser.bytes, id=payment.bytes)

            binding_sync = await repository.claim()
            assert binding_sync["owner_user_id"] == owner.bytes
            assert not await balance.claim_refresh(engine)
            history = await history_jobs.claim_history(engine)
            assert history["owner_user_id"] == owner.bytes
            assert await repository.complete(binding_sync, [], "SCHOOL_TIMEOUT", new_id())

            browser_refresh = await balance.claim_refresh(engine)
            assert browser_refresh["id"] == browser.bytes
            assert not await balance.claim_refresh(engine)
            assert await balance.finish_refresh(engine, browser_refresh, [], "SCHOOL_TIMEOUT")
            payment_refresh = await balance.claim_refresh(engine)
            assert payment_refresh["id"] == payment.bytes
            assert payment_refresh["saga_step"] == "read_school"
            assert payment_refresh["upstream_operation_id"] is None
    asyncio.run(case())


def test_payment_skips_busy_owner_cancel_and_restart_fence(monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")

    async def case():
        async with database("payment", production_pool=True) as engine:
            order, owner = await seed(engine)
            other, another = await seed(engine)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET owner_user_id=:owner WHERE id=:id",
                              owner=owner.bytes, id=other.bytes)
            entered, release = asyncio.Event(), asyncio.Event()

            async def call(*args, **kwargs):
                entered.set()
                await release.wait()
                return {"order_state": "status_unknown"}

            app = SimpleNamespace(state=SimpleNamespace(
                database=engine, service_client=SimpleNamespace(call=call)))
            task = asyncio.create_task(reconciliation.check_tick(app, order_id=order))
            await entered.wait()
            assert not await check_claims.claim(engine, other)
            free_order, free_owner = await seed(engine)
            async with asyncio.timeout(1):
                free = await check_claims.claim(engine)
            assert free["id"] == free_order.bytes and free["owner_user_id"] == free_owner.bytes
            await cancellation.cancel(engine, Principal("payment", owner, 1, new_id()), order, 1)
            release.set()
            assert await task
            await reconciliation.check_order(app, free)
            assert (await read(engine, order))["next_check_at"] is None
            assert not await check_claims.claim(engine, order)
            # 模拟进程消失后租约到期；迟到旧租约不得覆盖接管者。
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET check_lease_until=NULL "
                              "WHERE id=:id", id=order.bytes)
            old = await check_claims.claim(engine, other)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET check_lease_until="
                              "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE id=:id",
                              id=other.bytes)
            current = await check_claims.claim(engine, other)
            assert current["check_lease_owner"] != old["check_lease_owner"]
            await reconciliation.check_order(app, old)
            assert (await read(engine, other))["last_checked_at"] is None
            await reconciliation.check_order(app, current)
            assert (await read(engine, other))["last_checked_at"] is not None
            assert another != owner
    asyncio.run(case())


def test_bounded_owner_cursor_advances_past_locked_first_page():
    async def case():
        async with database("room") as engine:
            for index in range(1, 35):
                await RoomRepository(engine).accept_sync(UUID(int=index), str(new_id()))
            schedule = ReadSchedule(KINDS)
            async with engine.begin() as blocker:
                await execute(blocker, "SELECT owner_user_id FROM room_preferences "
                              "ORDER BY owner_user_id LIMIT 32 FOR UPDATE")
                assert not await RoomRepository(engine).claim(schedule)
                row = await RoomRepository(engine).claim(schedule)
                assert row["owner_user_id"] == UUID(int=33).bytes
    asyncio.run(case())


def test_stop_during_owner_recheck_prevents_task_claim(monkeypatch):
    async def case():
        async with database("room") as engine:
            await room_jobs(engine)
            stop = asyncio.Event()
            original = read_claims.lock_idle

            async def stopping(conn, owner, kind):
                valid = await original(conn, owner, kind)
                stop.set()
                return valid

            monkeypatch.setattr(read_claims, "lock_idle", stopping)
            assert not await history_jobs.claim_history(engine, stop=stop)
            stop.clear()
            assert not await balance.claim_refresh(engine, stop=stop)
            stop.clear()
            assert not await RoomRepository(engine).claim(stop=stop)
    asyncio.run(case())
