"""真实 MySQL 的快照复用、并发配额、旧 token 与有界清理。"""

import asyncio
import hashlib
from datetime import date

import pytest
from query_resource_support import counts, requires_mysql, run, seed_samples

from services.common.dates import utc_bounds
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import SampleQuery
from services.common.sql import execute, first
from services.monitoring import sample_snapshots as limits
from services.monitoring import snapshot_cleanup
from services.monitoring.samples import list_samples, snapshot

pytestmark = requires_mysql
TOKEN_KEY = b"synthetic-snapshot-key-for-isolated-test"
TABLES = ["sample_snapshots", "sample_snapshot_items"]


def query(binding, **kwargs):
    return SampleQuery(binding_id=binding, start_date=date(2026, 9, 1),
                       end_date=date(2026, 9, 30), page=1, page_size=1, **kwargs)


async def take(engine, owner, command, key=TOKEN_KEY):
    return await list_samples(engine, owner, command, key)


def test_parallel_reuse_late_sample_and_key_rotation():
    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_samples(engine, owner, binding)
        command = query(binding)
        pages = await asyncio.gather(*(take(engine, owner, command) for _ in range(8)))
        original = pages[0]
        assert len({page.snapshot_token for page in pages}) == 1
        assert await counts(engine, TABLES) == [1, 3]
        second = command.model_copy(update={"page": 2, "snapshot_token": original.snapshot_token})
        before = await take(engine, owner, second)
        # 同一采集时间的迟到提交，ID 不在旧成员集合内。
        async with engine.begin() as conn:
            row = await first(conn, "SELECT * FROM monitor_samples ORDER BY captured_at LIMIT 1")
            await execute(conn, "UPDATE monitor_runs SET scheduled_for=DATE_SUB("
                          "scheduled_for,INTERVAL 1 DAY) WHERE id=:id", id=row["run_id"])
        await seed_samples(engine, owner, binding, count=1)
        newer = await take(engine, owner, command)
        assert newer.total == 4 and newer.snapshot_token != original.snapshot_token
        after = await take(engine, owner, second)
        assert after.total == 3 and after.items == before.items
        rotated = await take(engine, owner, command, b"rotated-synthetic-key")
        assert rotated.snapshot_token != newer.snapshot_token
        assert (await take(engine, owner, second, b"rotated-synthetic-key")).items == before.items
    run("monitoring", case)


@pytest.mark.parametrize("budget,value", [
    ("CREATIONS_PER_MINUTE", 2), ("MAX_SNAPSHOTS", 2), ("MAX_MEMBERS", 6),
])
def test_concurrent_different_ranges_cannot_exceed_budget(monkeypatch, budget, value):
    monkeypatch.setattr(limits, budget, value)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_samples(engine, owner, binding)
        commands = [query(binding).model_copy(update={"end_date": date(2026, 9, day)})
                    for day in range(2, 8)]
        results = await asyncio.gather(*(take(engine, owner, cmd) for cmd in commands),
                                       return_exceptions=True)
        assert sum(not isinstance(result, Exception) for result in results) == 2
        assert all(isinstance(result, ApiError) and result.status == 429
                   for result in results if isinstance(result, Exception))
        assert await counts(engine, TABLES) == [2, 6]
    run("monitoring", case)


def test_member_limit_is_not_silent_truncation(monkeypatch):
    monkeypatch.setattr(limits, "MAX_SAMPLES", 2)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_samples(engine, owner, binding)
        with pytest.raises(ApiError) as error:
            await take(engine, owner, query(binding))
        assert error.value.status == 429
        assert await counts(engine, TABLES) == [0, 0]
    run("monitoring", case)


def test_expiry_bounded_cleanup_legacy_token_and_owner(monkeypatch):
    monkeypatch.setattr(snapshot_cleanup, "MEMBER_BATCH", 2)
    monkeypatch.setattr(snapshot_cleanup, "SNAPSHOT_BATCH", 1)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_samples(engine, owner, binding)
        command = query(binding)
        page = await take(engine, owner, command)
        token = "legacy-random-token-for-synthetic-test"
        async with engine.begin() as conn:
            await execute(conn, "UPDATE sample_snapshots SET token_hash=:hash,membership_hash=NULL",
                          hash=hashlib.sha256(token.encode()).digest())
        old = command.model_copy(update={"snapshot_token": token})
        assert (await take(engine, owner, old)).total == page.total
        with pytest.raises(ApiError) as other:
            await take(engine, new_id(), old)
        assert other.value.status == 404
        with pytest.raises(ApiError) as mismatch:
            await take(engine, owner, old.model_copy(update={"binding_id": new_id()}))
        assert mismatch.value.code == "SNAPSHOT_MISMATCH"
        async with engine.begin() as conn:
            await execute(conn, "UPDATE sample_snapshots SET expires_at=UTC_TIMESTAMP(6)")
        with pytest.raises(ApiError) as expired:
            await take(engine, owner, old)
        assert expired.value.status == 410
        await snapshot_cleanup.cleanup_snapshots(engine)
        assert await counts(engine, TABLES) == [1, 1]
        await snapshot_cleanup.cleanup_snapshots(engine)
        assert await counts(engine, TABLES) == [0, 0]
        assert await counts(engine, ["monitor_samples"]) == [3]
        # 清理完成可重新创建，活跃快照不会被清理。
        await take(engine, owner, command)
        assert not await snapshot_cleanup.cleanup_snapshots(engine)
        assert await counts(engine, TABLES) == [1, 3]
    run("monitoring", case)


def test_parallel_cleanup_skips_reader_lock_and_keeps_foreign_keys(monkeypatch):
    monkeypatch.setattr(snapshot_cleanup, "MEMBER_BATCH", 2)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_samples(engine, owner, binding)
        await take(engine, owner, query(binding))
        async with engine.begin() as conn:
            await execute(conn, "UPDATE sample_snapshots SET expires_at=UTC_TIMESTAMP(6)")
        async with engine.begin() as reader:
            # 实际分页读取完整父行；仅投影id会被新增覆盖索引改成索引记录锁。
            await execute(reader, "SELECT * FROM sample_snapshots FOR SHARE")
            assert not await snapshot_cleanup.cleanup_snapshots(engine)
            assert await counts(engine, TABLES) == [1, 3]
        await asyncio.gather(snapshot_cleanup.cleanup_snapshots(engine),
                             snapshot_cleanup.cleanup_snapshots(engine))
        await snapshot_cleanup.cleanup_snapshots(engine)
        assert await counts(engine, TABLES) == [0, 0]
        assert await counts(engine, ["monitor_samples"]) == [3]
    run("monitoring", case)


def test_insert_failure_rolls_back_snapshot(monkeypatch):
    original_first = limits.first

    async def fail(conn, statement, **params):
        if statement == "SELECT * FROM sample_snapshots WHERE id=:id":
            raise RuntimeError("synthetic failure after header insert")
        return await original_first(conn, statement, **params)

    async def case(engine):
        owner, binding = new_id(), new_id()
        command = query(binding)
        monkeypatch.setattr(limits, "first", fail)
        with pytest.raises(RuntimeError):
            async with engine.begin() as conn:
                await snapshot(conn, owner, command, *utc_bounds(command.start_date,
                               command.end_date), TOKEN_KEY)
        assert await counts(engine, TABLES) == [0, 0]
    run("monitoring", case)
