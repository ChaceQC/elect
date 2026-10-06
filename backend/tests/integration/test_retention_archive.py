"""R4归档/去重180天边界、失败关闭、真实事务与旧键恢复。"""

import asyncio
import hashlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from query_resource_support import counts, database, requires_mysql, seed_binding, seed_samples
from sqlalchemy.exc import ProgrammingError

from services.common import archive_store
from services.common.archive_verify import verify_archives, verify_cold_links
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.outbox import consume_once
from services.common.sql import execute, first
from services.deployment.retention import batch
from services.monitoring.runs import run_view
from services.monitoring.scheduler import accept_run
from services.room.balance import accept_refresh
from services.room.repository import RoomRepository

pytestmark = requires_mysql
FUTURE = datetime(9999, 1, 1)


async def age(conn, table, days, condition="1=1"):
    await execute(conn, f"UPDATE {table} SET created_at=DATE_SUB(UTC_TIMESTAMP(6),"
                  f"INTERVAL :days DAY),updated_at=created_at WHERE {condition}", days=days)


def test_room_179_180_original_key_owner_digest_and_corruption():
    async def case():
        async with database("room", production_pool=True) as engine:
            owner, binding, key = new_id(), new_id(), str(new_id())
            await seed_binding(engine, owner, binding)
            op = await accept_refresh(engine, owner, binding, key)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE room_operations SET state='succeeded',"
                              "saga_step='complete',next_reconcile_at=NULL")
                await age(conn, "room_operations", 179)
            report = await batch(engine, "room", "room_operations", FUTURE, apply=True)
            assert report["archived"] == 0
            async with engine.begin() as conn:
                await age(conn, "room_operations", 180)
            assert (await batch(engine, "room", "room_operations", FUTURE))["eligible"] == 1
            assert await counts(engine, ["room_operations", "archive_records"]) == [1, 0]
            report = await batch(engine, "room", "room_operations", FUTURE, apply=True)
            assert report["archived"] == 1
            assert await accept_refresh(engine, owner, binding, key) == op
            view = await RoomRepository(engine).operation(owner, op)
            assert view["state"] == "succeeded"
            with pytest.raises(ApiError) as error:
                await RoomRepository(engine).operation(new_id(), op)
            assert error.value.status == 404
            with pytest.raises(ApiError) as error:
                await accept_refresh(engine, owner, new_id(), key)
            assert error.value.status == 409
            async with engine.begin() as conn:
                assert await verify_archives(conn) == 1
                await verify_cold_links(conn)
                await execute(conn, "UPDATE archive_records SET payload=:broken", broken=b"broken")
            with pytest.raises(ApiError) as error:
                await accept_refresh(engine, owner, binding, key)
            assert error.value.status == 503
            assert await counts(engine, ["room_operations", "cold_request_keys"]) == [0, 1]
    asyncio.run(case())


def test_room_fk_unknown_and_readback_failure_keep_hot(monkeypatch):
    async def case():
        async with database("room") as engine:
            owner, binding = new_id(), new_id()
            await seed_binding(engine, owner, binding)
            op = await accept_refresh(engine, owner, binding, str(new_id()))
            async with engine.begin() as conn:
                await execute(conn, "UPDATE room_operations SET state='succeeded',"
                              "next_reconcile_at=NULL")
                await age(conn, "room_operations", 181)
                await execute(conn, "UPDATE room_preferences SET switch_operation_id=:id",
                              id=op.bytes)
            report = await batch(engine, "room", "room_operations", FUTURE, apply=True)
            assert report["retained"] == 1
            async with engine.begin() as conn:
                await execute(conn, "UPDATE room_preferences SET switch_operation_id=NULL")
            def fail(_):
                raise archive_store.unavailable()
            monkeypatch.setattr(archive_store, "unpack", fail)
            with pytest.raises(ApiError):
                await batch(engine, "room", "room_operations", FUTURE, apply=True)
            assert await counts(engine, ["room_operations", "archive_records"]) == [1, 0]
            async with engine.begin() as conn:
                await execute(conn, "UPDATE room_operations SET state='unknown'")
            report = await batch(engine, "room", "room_operations", FUTURE, apply=True)
            assert report["candidates"] == 0
    asyncio.run(case())


def test_monitor_legacy_seven_days_and_attempts_transparent_read():
    async def case():
        async with database("monitoring") as engine:
            owner, binding, key = new_id(), new_id(), str(new_id())
            await seed_samples(engine, owner, binding, 1)
            async with engine.begin() as conn:
                run = await first(conn, "SELECT * FROM monitor_runs LIMIT 1")
                await execute(conn, "INSERT INTO monitor_run_requests (owner_user_id,"
                    "idempotency_key_hash,request_digest,run_id,expires_at) "
                    "VALUES (:owner,:key,:digest,:run,DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 172 DAY))",
                    owner=owner.bytes, key=hashlib.sha256(key.encode()).digest(),
                    digest=hashlib.sha256(b"manual_run").digest(), run=run["id"])
                await age(conn, "monitor_runs", 181)
                await age(conn, "monitor_run_requests", 179)
            assert (await batch(engine, "monitoring", "monitor_run_requests", FUTURE,
                                apply=True))["archived"] == 0
            async with engine.begin() as conn:
                await age(conn, "monitor_run_requests", 180)
                await execute(conn, "INSERT INTO monitor_attempts (id,run_id,attempt_no,worker_id,"
                    "execution_epoch,started_at,finished_at,outcome) VALUES "
                    "(:id,:run,1,'synthetic',1,:start,:end,'succeeded')", id=new_id().bytes,
                    run=run["id"], start=datetime.now()-timedelta(days=181),
                    end=datetime.now()-timedelta(days=181))
                await age(conn, "monitor_attempts", 181)
                before = await run_view(conn, run)
            await batch(engine, "monitoring", "monitor_run_requests", FUTURE, apply=True)
            assert (await accept_run(engine, owner, key, new_id()))["id"] == run["id"]
            await batch(engine, "monitoring", "monitor_attempts", FUTURE, apply=True)
            async with engine.begin() as conn:
                assert await run_view(conn, run) == before
                await verify_cold_links(conn)
            assert await counts(engine, ["monitor_attempts", "monitor_samples"]) == [0, 1]
    asyncio.run(case())


def test_inbox_concurrent_redelivery_hot_cold_and_missing_cold_table():
    async def case():
        async with database("audit", production_pool=True) as engine:
            event = SimpleNamespace(event_id=new_id())
            calls = []
            async def handler(conn, value):
                calls.append(value.event_id)
            assert await consume_once(engine, "synthetic", event, handler)
            async with engine.begin() as conn:
                await age(conn, "inbox_events", 180)
                await execute(conn, "UPDATE inbox_events SET processed_at=created_at")
            results = await asyncio.gather(
                batch(engine, "audit", "inbox_events", FUTURE, apply=True),
                *(consume_once(engine, "synthetic", event, handler) for _ in range(5)),
                return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    assert getattr(result, "orig", None).args[0] == 1213
            # 数据库死锁拒绝的事务由原MQ重投，绝不当作业务已执行。
            await batch(engine, "audit", "inbox_events", FUTURE, apply=True)
            assert calls == [event.event_id]
            assert not await consume_once(engine, "synthetic", event, handler)
            assert await counts(engine, ["inbox_events", "cold_inbox_events"]) == [1, 1]
            async with engine.begin() as conn:
                await verify_cold_links(conn)
                await execute(conn, "DELETE FROM inbox_events")
                await execute(conn, "RENAME TABLE cold_inbox_events TO unavailable_inbox")
            with pytest.raises(ProgrammingError):
                await consume_once(engine, "synthetic", event, handler)
            assert calls == [event.event_id]
            assert await counts(engine, ["inbox_events"]) == [0]
    asyncio.run(case())


def test_published_outbox_boundary_keeps_unpublished_and_repeated_cold_marker():
    async def case():
        async with database("audit") as engine:
            old, young, pending = new_id(), new_id(), new_id()
            async with engine.begin() as conn:
                for event, days, published in ((old, 180, True), (young, 179, True),
                                                (pending, 181, False)):
                    await execute(conn, "INSERT INTO outbox_events (event_id,type,schema_version,"
                        "aggregate_id,aggregate_version,payload,available_at,publish_attempts,"
                        "created_at,published_at) VALUES (:id,'synthetic',1,:id,1,'{}',"
                        "UTC_TIMESTAMP(6),1,DATE_SUB(UTC_TIMESTAMP(6),INTERVAL :days DAY),"
                        "IF(:published,DATE_SUB(UTC_TIMESTAMP(6),INTERVAL :days DAY),NULL))",
                        id=event.bytes, days=days, published=published)
            result = await batch(engine, "audit", "outbox_events", FUTURE, apply=True)
            assert result["archived"] == 1
            assert await counts(engine, ["outbox_events", "archive_records"]) == [2, 1]
            event = SimpleNamespace(event_id=new_id())
            calls = []
            async def handler(conn, value):
                calls.append(value.event_id)
            await consume_once(engine, "again", event, handler)
            for _ in range(2):
                async with engine.begin() as conn:
                    await age(conn, "inbox_events", 181)
                    await execute(conn, "UPDATE inbox_events SET processed_at=created_at")
                await batch(engine, "audit", "inbox_events", FUTURE, apply=True)
                assert not await consume_once(engine, "again", event, handler)
            assert calls == [event.event_id]
    asyncio.run(case())
