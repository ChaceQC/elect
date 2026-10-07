"""旧QR迁移保守时间、跨订单预算和冷键恢复；不调用学校。"""

import asyncio
import hashlib
from datetime import datetime

import pytest
from query_resource_support import counts, database, migrate, requires_mysql
from test_payment_polling import seed

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.deployment.retention import batch
from services.payment.qr import refresh

pytestmark = requires_mysql
FUTURE = datetime(9999, 1, 1)


def test_legacy_qr_conservative_time_unknown_protection_cold_replay():
    async def case():
        async with database("payment", revision="payment_0004") as engine:
            order, owner = await seed(engine)
            key = str(new_id())
            digest = hashlib.sha256(f"qr:{order}".encode()).digest()
            async with engine.begin() as conn:
                op = await first(conn, "SELECT id FROM payment_operations WHERE order_id=:id",
                                 id=order.bytes)
                await execute(conn, "INSERT INTO payment_qr_requests "
                    "(owner_user_id,key_hash,request_digest,operation_id) "
                    "VALUES (:owner,:key,:digest,:op)", owner=owner.bytes,
                    key=hashlib.sha256(key.encode()).digest(), digest=digest, op=op["id"])
                before = (await first(conn, "SELECT UTC_TIMESTAMP(6) AS now"))["now"]
                await conn.run_sync(migrate, "payment")
                await conn.run_sync(migrate, "payment")
                row = await first(conn, "SELECT created_at FROM payment_qr_requests")
                assert row["created_at"] >= before
                await execute(conn, "UPDATE payment_operations SET state='succeeded',"
                    "created_at='2000-01-01',updated_at='2000-01-01',next_attempt_at=NULL")
                await execute(conn, "UPDATE payment_orders SET state='paid_confirmed',"
                    "next_check_at=NULL,balance_refresh_state='succeeded'")
            assert (await batch(engine, "payment", "payment_qr_requests", FUTURE,
                                apply=True))["archived"] == 0
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_qr_requests SET created_at='2000-01-01'")
                await execute(conn, "UPDATE payment_orders SET state='status_unknown'")
            assert (await batch(engine, "payment", "payment_qr_requests", FUTURE,
                                apply=True))["archived"] == 0
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET state='paid_confirmed'")
            dry = await batch(engine, "payment", "payment_qr_requests", FUTURE, limit=1)
            assert dry["candidates"] == 1
            assert await counts(engine, ["payment_qr_requests", "cold_request_keys"]) == [1, 0]
            result = await batch(engine, "payment", "payment_qr_requests", FUTURE,
                                 apply=True, limit=1)
            assert result["archived"] == 1 and result["cursor"]
            again = await batch(engine, "payment", "payment_qr_requests", FUTURE,
                                apply=True, after=result["cursor"])
            assert again["candidates"] == 0
            replay = await refresh(engine, owner, order, key)
            assert replay.operation_id.bytes == op["id"] and replay.state == "succeeded"
            with pytest.raises(ApiError) as error:
                await refresh(engine, new_id(), order, key)
            assert error.value.status == 404
    asyncio.run(case())


def test_qr_different_orders_share_daily_budget():
    async def case():
        async with database("payment") as engine:
            first_order, owner = await seed(engine)
            other_order, other_owner = await seed(engine)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET owner_user_id=:owner WHERE id=:id",
                              owner=owner.bytes, id=other_order.bytes)
                await execute(conn, "UPDATE payment_operations SET owner_user_id=:owner "
                              "WHERE order_id=:id", owner=owner.bytes, id=other_order.bytes)
            for _ in range(6):
                await refresh(engine, owner, first_order, str(new_id()))
            with pytest.raises(ApiError) as error:
                await refresh(engine, owner, other_order, str(new_id()))
            assert error.value.status == 429
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_operations SET state='succeeded'")
                await execute(conn, "UPDATE payment_qr_requests SET created_at="
                              "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 2 MINUTE)")
                original = await first(conn, "SELECT * FROM payment_qr_requests LIMIT 1")
                for _ in range(54):
                    await execute(conn, "INSERT INTO payment_qr_requests "
                        "(owner_user_id,key_hash,request_digest,operation_id,created_at) "
                        "VALUES (:owner,:key,:digest,:op,"
                        "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 2 MINUTE))",
                        owner=owner.bytes, key=hashlib.sha256(new_id().bytes).digest(),
                        digest=original["request_digest"], op=original["operation_id"])
            with pytest.raises(ApiError) as error:
                await refresh(engine, owner, other_order, str(new_id()))
            assert error.value.retry_after_seconds > 86000
            third, third_owner = await seed(engine)
            assert third_owner != other_owner
            assert await refresh(engine, third_owner, third, str(new_id()))
    asyncio.run(case())
