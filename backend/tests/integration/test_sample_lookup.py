"""R5.2实际分页SQL、MySQL8.4执行计划与增量索引成本。"""

import asyncio
import hashlib
import json
from datetime import date
from time import perf_counter

from query_resource_support import database, migrate, requires_mysql, seed_samples
from sample_lookup_support import handlers, seed

from services.common.ids import new_id
from services.common.internal_dto import SampleQuery
from services.common.sql import execute, first
from services.monitoring.samples import PAGE_SQL, list_samples

pytestmark = requires_mysql


def test_repeated_key_uses_all_earlier_history_and_keeps_fixed_total():
    async def case():
        async with database("monitoring") as engine:
            owner, other, binding = new_id(), new_id(), new_id()
            await seed_samples(engine, owner, binding, 6)
            await seed_samples(engine, other, binding, 1)
            async with engine.begin() as conn:
                rows = (await execute(conn, "SELECT id FROM monitor_samples WHERE "
                                      "owner_user_id=:owner ORDER BY captured_at,id",
                                      owner=owner.bytes)).scalars().all()
                for sid, key in zip(rows, ["repeat", None, "", "unique", "repeat", "same-time"],
                                    strict=True):
                    await execute(conn, "UPDATE monitor_samples SET meter_source_record_key=:key "
                                  "WHERE id=:id", id=sid, key=key)
                # 同时间戳的不同ID不构成更早观测；跨owner相同key也不构成重复。
                await execute(conn, "UPDATE monitor_samples SET captured_at='2026-09-01 00:05:00',"
                              "meter_source_record_key='same-time' WHERE id=:id", id=rows[3])
                await execute(conn, "UPDATE monitor_samples SET meter_source_record_key='repeat',"
                              "captured_at='2026-08-01' WHERE owner_user_id=:owner",
                              owner=other.bytes)
            command = SampleQuery(binding_id=binding, start_date=date(2026, 9, 1),
                                   end_date=date(2026, 9, 1), page=1, page_size=2)
            first_page = await list_samples(engine, owner, command, b"synthetic-key")
            items = list(first_page.items)
            for page in (2, 3):
                value = await list_samples(engine, owner, command.model_copy(update={
                    "page": page, "snapshot_token": first_page.snapshot_token}), b"synthetic-key")
                assert value.total == 6 and value.has_monitor_history
                items.extend(value.items)
            by_id = {item.id.bytes: item for item in items}
            assert by_id[rows[4]].meter_is_repeated
            assert all(not by_id[sid].meter_is_repeated for sid in rows if sid != rows[4])
    asyncio.run(case())


def test_long_term_index_plan_scan_latency_and_write_cost(monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")

    async def measure(conn, params):
        before = await handlers(conn)
        start = perf_counter()
        rows = (await execute(conn, PAGE_SQL, **params)).mappings().all()
        seconds = perf_counter() - start
        after = await handlers(conn)
        await execute(conn, "EXPLAIN ANALYZE " + PAGE_SQL, **params)
        explained = await execute(conn, "EXPLAIN FORMAT=JSON " + PAGE_SQL, **params)
        plan = json.loads(explained.scalar())
        return rows, seconds, sum(after[k] - before[k] for k in before), plan

    async def case():
        async with database("monitoring", production_pool=True,
                            revision="monitoring_0009") as engine:
            owner, binding = new_id(), new_id()
            monitor = await seed(engine, owner, binding, 20000)
            command = SampleQuery(binding_id=binding, start_date=date(2026, 9, 1),
                                   end_date=date(2026, 9, 30), page=1, page_size=100)
            page = await list_samples(engine, owner, command, b"synthetic-key")
            async with engine.begin() as conn:
                fixed = await first(conn, "SELECT id FROM sample_snapshots WHERE token_hash=:hash",
                                    hash=hashlib.sha256(page.snapshot_token.encode()).digest())
                params = {"snapshot": fixed["id"], "offset": 0, "size": 100}
                old = await measure(conn, params)
            start = perf_counter()
            await seed(engine, owner, binding, 250, offset=20000, monitor=monitor)
            old_write = perf_counter() - start
            started = asyncio.Event()

            async def upgrade():
                start = perf_counter()
                async with engine.begin() as conn:
                    started.set()
                    await conn.run_sync(migrate, "monitoring")
                return perf_counter() - start
            async with engine.begin() as blocker:
                await execute(blocker, "SELECT id FROM monitor_samples LIMIT 1")
                migrating = asyncio.create_task(upgrade())
                await started.wait()
                await asyncio.sleep(0.05)
                assert not migrating.done()  # 实际元数据锁窗口；不能宣称DDL无阻塞。
            ddl = await migrating
            async with engine.begin() as conn:
                await execute(conn, "ANALYZE TABLE monitor_samples")
                new = await measure(conn, params)
                stats = await first(conn, "SELECT SUM(stat_value)*@@innodb_page_size AS bytes "
                                    "FROM mysql.innodb_index_stats WHERE database_name=DATABASE() "
                                    "AND table_name='monitor_samples' AND "
                                    "index_name='ix_sample_meter_lookup' AND stat_name='size'")
                original = await execute(conn, "SHOW INDEX FROM monitor_samples "
                                         "WHERE Key_name='ix_monitor_samples_0'")
                assert len(original.all()) == 4
            start = perf_counter()
            await seed(engine, owner, binding, 250, offset=20250, monitor=monitor)
            new_write = perf_counter() - start
            assert old[0] == new[0] and len(new[0]) == 100
            assert "ix_sample_meter_lookup" in json.dumps(new[3])
            assert new[2] < old[2] / 10
            print(f"R5 samples rows=20000 page=100 handlers={old[2]}->{new[2]} "
                  f"seconds={old[1]:.4f}->{new[1]:.4f} ddl_seconds={ddl:.4f} "
                  f"index_bytes={stats['bytes']} "
                  f"insert250_seconds={old_write:.4f}->{new_write:.4f}")
            # 计划仅输出执行结构，绑定参数仍是随机合成值。
            def lookup(value):
                if isinstance(value, dict):
                    if value.get("table_name") == "other":
                        return {k: value.get(k) for k in ("access_type", "key",
                                                       "rows_examined_per_scan")}
                    return next((found for part in value.values() if (found := lookup(part))), None)
                if isinstance(value, list):
                    return next((found for part in value if (found := lookup(part))), None)
            print("R5 lookup plans", lookup(old[3]), lookup(new[3]))
    asyncio.run(case())
