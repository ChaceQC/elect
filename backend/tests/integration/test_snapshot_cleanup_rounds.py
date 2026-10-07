"""20,000成员积压、owner公平、共享锁与中断续跑的一次对照。"""

import asyncio
import time
from datetime import datetime, timedelta

from query_resource_support import counts, database, requires_mysql, seed_samples
from sqlalchemy import text
from test_snapshot_admission import query, take

from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.snapshot_cleanup import SnapshotCleaner

pytestmark = requires_mysql


async def expand(conn, row):
    sample = await first(conn, "SELECT * FROM monitor_samples WHERE id=:id", id=row["sample_id"])
    for start in range(2, 20001, 500):
        records = [{"id": new_id().bytes, "sample": new_id().bytes, "position": pos,
                    "monitor": sample["monitor_id"], "owner": sample["owner_user_id"],
                    "binding": sample["binding_id"], "snapshot": row["snapshot_id"],
                    "time": datetime(2026, 9, 1) + timedelta(seconds=pos)}
                   for pos in range(start, min(start + 500, 20001))]
        await conn.execute(text("INSERT INTO monitor_runs (id,monitor_id,generation,"
            "scheduled_for,binding_id,credential_version,state,version,attempt_count,"
            "execution_epoch) VALUES (:id,:monitor,1,:time,:binding,1,'succeeded',1,0,1)"), records)
        await conn.execute(text("INSERT INTO monitor_samples (id,run_id,monitor_id,owner_user_id,"
            "binding_id,captured_at,balance,quality,credential_version) VALUES "
            "(:sample,:id,:monitor,:owner,:binding,:time,25.50,'balance_only',1)"), records)
        await conn.execute(text("INSERT INTO sample_snapshot_items "
                               "(snapshot_id,position,sample_id) "
                               "VALUES (:snapshot,:position,:sample)"), records)


def test_large_backlog_fairness_locked_reader_stop_and_resume():
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owners = [new_id(), new_id()]
            for owner in owners:
                binding = new_id()
                await seed_samples(engine, owner, binding, 1)
                await take(engine, owner, query(binding))
            async with engine.begin() as conn:
                row = await first(conn, "SELECT * FROM sample_snapshot_items "
                                  "ORDER BY snapshot_id LIMIT 1")
                await expand(conn, row)
                await execute(conn, "UPDATE sample_snapshots SET total=20000 WHERE id=:id",
                              id=row["snapshot_id"])
                await execute(conn, "UPDATE sample_snapshots SET expires_at=DATE_SUB("
                              "UTC_TIMESTAMP(6),INTERVAL 1 SECOND)")
                plan = (await execute(conn, "EXPLAIN SELECT id FROM sample_snapshots "
                    "WHERE owner_user_id>:owner AND expires_at<=UTC_TIMESTAMP(6) "
                    "ORDER BY owner_user_id,expires_at,id LIMIT 64", owner=b"")).mappings().first()
                assert "ix_snapshot_owner_expiry" in (plan["possible_keys"] or "")
                assert plan["key"] == "ix_snapshot_owner_expiry"
            cleaner, stop = SnapshotCleaner(), asyncio.Event()
            async with engine.begin() as reader:
                await execute(reader, "SELECT id FROM sample_snapshots WHERE id=:id FOR SHARE",
                              id=row["snapshot_id"])
                batch = await cleaner.batch(engine)
                assert batch.skipped_locks == 1 and batch.parents == 1
            assert await counts(engine, ["sample_snapshots", "sample_snapshot_items"]) == [1, 20000]
            stop.set()
            await cleaner.round(engine, stop)
            assert await counts(engine, ["sample_snapshot_items"]) == [20000]
            # 模拟进程重启丢失游标，数据仍由数据库和父锁决定。
            cleaner, stop = SnapshotCleaner(), asyncio.Event()
            started, rounds = time.monotonic(), 0
            while (await counts(engine, ["sample_snapshots"]))[0]:
                delay = await cleaner.round(engine, stop)
                assert delay in {1, 60}
                rounds += 1
                assert rounds < 30
                if (await counts(engine, ["sample_snapshots"]))[0]:
                    await asyncio.sleep(delay)
            elapsed = time.monotonic() - started
            assert await counts(engine, ["monitor_samples"]) == [20001]
            assert await cleaner.round(engine, stop) == 60
            print(f"R4 snapshot members=20000 rounds={rounds} elapsed_seconds={elapsed:.3f} "
                  f"members_per_second={20000/elapsed:.1f} "
                  "old_schedule_wait_derived_seconds=1140")
    asyncio.run(case())
