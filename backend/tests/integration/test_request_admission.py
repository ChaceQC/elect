"""R4三域真实MySQL并发预算与拒绝回滚；只造合成请求。"""

import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from query_resource_support import counts, database, requires_mysql, seed_binding
from sqlalchemy import text
from test_payment_polling import seed as payment_seed

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import PaymentBalanceRefresh
from services.common.security import Principal
from services.common.sql import execute
from services.monitoring.repository import lock_monitor
from services.monitoring.scheduler import accept_run
from services.payment.qr import refresh
from services.room.balance import accept_refresh
from services.room.query_api import payment_refresh

pytestmark = requires_mysql


@pytest.mark.parametrize("domain", ["room", "monitoring", "payment"])
def test_parallel_new_keys_replay_pending_and_rejection_rollback(domain):
    async def case():
        async with database(domain, production_pool=True) as engine:
            owner, binding = new_id(), new_id()
            if domain == "room":
                await seed_binding(engine, owner, binding)
                async def submit(key):
                    return await accept_refresh(engine, owner, binding, key)
                tables = ["room_operations", "outbox_events"]
                table = "room_operations"
            elif domain == "monitoring":
                async with engine.begin() as conn:
                    await lock_monitor(conn, owner)
                    await execute(conn, "UPDATE monitors SET state='active',desired_enabled=1,"
                                  "credential_allowed=1,credential_version=1,"
                                  "credential_ref=:binding,binding_id=:binding "
                                  "WHERE owner_user_id=:owner", owner=owner.bytes,
                                  binding=binding.bytes)
                async def submit(key):
                    return await accept_run(engine, owner, key, new_id())
                tables = ["monitor_run_requests", "monitor_runs", "outbox_events"]
                table = "monitor_run_requests"
            else:
                order, owner = await payment_seed(engine)
                async def submit(key):
                    return await refresh(engine, owner, order, key)
                tables = ["payment_qr_requests", "payment_operations", "outbox_events"]
                table = "payment_qr_requests"
            keys = [str(new_id()) for _ in range(12)]
            results = await asyncio.gather(*(submit(key) for key in keys), return_exceptions=True)
            assert sum(not isinstance(value, Exception) for value in results) == 6
            assert all(isinstance(value, ApiError) and value.status == 429
                       and value.retry_after_seconds > 0 for value in results
                       if isinstance(value, Exception))
            before = await counts(engine, tables)
            for key, value in zip(keys, results, strict=True):
                if not isinstance(value, Exception):
                    assert await submit(key) == value
            assert await counts(engine, tables) == before
            async with engine.begin() as conn:
                await execute(conn, f"UPDATE {table} SET created_at=DATE_SUB(UTC_TIMESTAMP(6),"
                              "INTERVAL 2 MINUTE)")
            for _ in range(2):
                await submit(str(new_id()))
            before = await counts(engine, tables)
            with pytest.raises(ApiError) as error:
                await submit(str(new_id()))
            assert error.value.status == 429
            assert await counts(engine, tables) == before
    asyncio.run(case())


def test_legacy_many_balance_aliases_commit_in_bounded_batches():
    from services.common.sql import first
    from services.room.balance import claim_refresh, finish_refresh
    from services.room.balance_store import settle_aliases

    async def case():
        async with database("room", production_pool=True) as engine:
            owner, binding = new_id(), new_id()
            await seed_binding(engine, owner, binding)
            root = await accept_refresh(engine, owner, binding, str(new_id()))
            async with engine.begin() as conn:
                target = await first(conn, "SELECT b.room_id,r.school_room_id FROM room_bindings b "
                    "JOIN rooms r ON r.id=b.room_id WHERE b.id=:id", id=binding.bytes)
                await conn.execute(text("INSERT INTO room_operations "
                    "(id,owner_user_id,type,target_room_id,target_binding_id,idempotency_key_hash,"
                    "request_digest,state,saga_step,upstream_operation_id) VALUES "
                    "(:id,:owner,'balance_refresh',:room,:binding,:key,:digest,'accepted','merged',:root)"),
                    [{"id": new_id().bytes, "owner": owner.bytes, "room": target["room_id"],
                      "binding": binding.bytes, "key": hashlib.sha256(new_id().bytes).digest(),
                      "digest": b"0"*32, "root": root.bytes} for _ in range(600)])
            row = await claim_refresh(engine)
            await finish_refresh(engine, row,
                                 [{"room_id": target["school_room_id"], "balance": "10.00"}], None)
            async with engine.connect() as conn:
                assert (await first(conn, "SELECT state FROM room_operations WHERE id=:id",
                                    id=root.bytes))["state"] == "succeeded"
                assert (await first(conn, "SELECT COUNT(*) AS n FROM room_operations "
                                    "WHERE state='succeeded'"))["n"] == 250
            assert await settle_aliases(engine)
            assert await settle_aliases(engine)
            assert not await settle_aliases(engine)
            async with engine.connect() as conn:
                assert (await first(conn, "SELECT COUNT(*) AS n FROM room_operations "
                                    "WHERE state='succeeded'"))["n"] == 601
    asyncio.run(case())


def test_balance_cross_binding_owner_and_system_source():
    async def case():
        async with database("room", production_pool=True) as engine:
            owner, other, binding, second = (new_id() for _ in range(4))
            await seed_binding(engine, owner, binding)
            await seed_binding(engine, owner, second)
            for _ in range(6):
                await accept_refresh(engine, owner, binding, str(new_id()))
            with pytest.raises(ApiError) as error:
                await accept_refresh(engine, owner, second, "payment-paid:pretend")
            assert error.value.status == 429
            request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=engine)))
            command = PaymentBalanceRefresh(binding_id=second, order_id=new_id())
            with pytest.raises(ApiError) as error:
                await payment_refresh(command, request, Principal("gateway", owner, 1, new_id()))
            assert error.value.status == 404
            result = await payment_refresh(
                command, request, Principal("payment", owner, 1, new_id()))
            assert result == await payment_refresh(
                command, request, Principal("payment", owner, 1, new_id()))
            with pytest.raises(ApiError) as error:
                await accept_refresh(engine, other, binding, str(new_id()))
            assert error.value.status == 404
            third = new_id()
            await seed_binding(engine, other, third)
            assert await accept_refresh(engine, other, third, str(new_id()))
    asyncio.run(case())
