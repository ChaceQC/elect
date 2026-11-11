"""真实 MySQL 验证历史受理预算、幂等、覆盖合并与事务回滚。"""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from query_resource_support import counts, requires_mysql, run, seed_binding

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.room import history_admission as limits
from services.room import history_jobs

pytestmark = requires_mysql
TABLES = ["room_operations", "history_syncs", "history_sync_windows", "outbox_events"]


def request(start=1, end=7):
    return SimpleNamespace(start_date=date(2026, 9, start), end_date=date(2026, 9, end))


async def accept(engine, owner, binding, command=None, key=None):
    return await history_jobs.accept_history(engine, owner, binding, command or request(),
                                            key or str(new_id()), new_id())


def test_idempotent_replay_and_covering_range_merge():
    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        key = str(new_id())
        original = await accept(engine, owner, binding, request(1, 14), key)
        assert await accept(engine, owner, binding, request(1, 14), key) == original
        with pytest.raises(ApiError) as conflict:
            await accept(engine, owner, binding, request(), key)
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
        merged = await accept(engine, owner, binding, request(3, 8))
        assert merged != original
        assert await counts(engine, TABLES) == [2, 1, 2, 1]
        async with engine.begin() as conn:
            row = await first(conn, "SELECT * FROM room_operations WHERE id=:id", id=merged.bytes)
            assert row["saga_step"] == "merged" and row["upstream_operation_id"] == original.bytes
    run("room", case)


@pytest.mark.parametrize("budget", ["OPERATIONS_PER_MINUTE", "OPERATIONS_PER_DAY",
                                    "MAX_PENDING_OPERATIONS"])
def test_parallel_aliases_are_bounded_and_replay_survives(monkeypatch, budget):
    monkeypatch.setattr(limits, budget, 3)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        key = str(new_id())
        original = await accept(engine, owner, binding, key=key)
        results = await asyncio.gather(*(accept(engine, owner, binding) for _ in range(7)),
                                       return_exceptions=True)
        assert sum(not isinstance(result, Exception) for result in results) == 2
        assert all(isinstance(result, ApiError) and result.status == 429
                   and result.retry_after_seconds >= 1
                   for result in results if isinstance(result, Exception))
        assert await counts(engine, TABLES) == [3, 1, 1, 1]
        assert await accept(engine, owner, binding, key=key) == original
    run("room", case)


def test_retry_wait_uses_larger_remaining_minute_or_day_window(monkeypatch):
    monkeypatch.setattr(limits, "OPERATIONS_PER_MINUTE", 1)
    monkeypatch.setattr(limits, "OPERATIONS_PER_DAY", 2)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        first_operation = await accept(engine, owner, binding)
        async with engine.begin() as conn:
            await execute(conn, "UPDATE room_operations SET created_at=DATE_SUB("
                          "UTC_TIMESTAMP(6),INTERVAL 2 MINUTE) WHERE id=:id",
                          id=first_operation.bytes)
        second_operation = await accept(engine, owner, binding)
        async with engine.begin() as conn:
            await execute(conn, "UPDATE room_operations SET created_at=DATE_SUB("
                          "UTC_TIMESTAMP(6),INTERVAL 86395 SECOND) WHERE id=:id",
                          id=first_operation.bytes)
            await execute(conn, "UPDATE room_operations SET created_at=DATE_SUB("
                          "UTC_TIMESTAMP(6),INTERVAL 45 SECOND) WHERE id=:id",
                          id=second_operation.bytes)
        with pytest.raises(ApiError) as limited_by_minute:
            await accept(engine, owner, binding)
        assert 12 <= limited_by_minute.value.retry_after_seconds <= 15
        async with engine.begin() as conn:
            await execute(conn, "UPDATE room_operations SET created_at=DATE_SUB("
                          "UTC_TIMESTAMP(6),INTERVAL 86370 SECOND) WHERE id=:id",
                          id=first_operation.bytes)
            await execute(conn, "UPDATE room_operations SET created_at=DATE_SUB("
                          "UTC_TIMESTAMP(6),INTERVAL 59 SECOND) WHERE id=:id",
                          id=second_operation.bytes)
        with pytest.raises(ApiError) as limited_by_day:
            await accept(engine, owner, binding)
        assert 27 <= limited_by_day.value.retry_after_seconds <= 30
        assert await counts(engine, TABLES) == [2, 1, 1, 1]
    run("room", case)


@pytest.mark.parametrize("budget,value,expected", [
    ("MAX_PENDING_SYNCS", 2, 2), ("MAX_PENDING_WINDOWS", 1, 1),
])
def test_parallel_ranges_and_bindings_share_owner_budget(monkeypatch, budget, value, expected):
    monkeypatch.setattr(limits, budget, value)

    async def case(engine):
        owner = new_id()
        bindings = [new_id() for _ in range(6)]
        for binding in bindings:
            await seed_binding(engine, owner, binding)
        results = await asyncio.gather(*(accept(engine, owner, binding) for binding in bindings),
                                       return_exceptions=True)
        assert sum(not isinstance(result, Exception) for result in results) == expected
        assert all(isinstance(result, ApiError) and result.status == 429
                   for result in results if isinstance(result, Exception))
        assert await counts(engine, TABLES) == [expected] * 4
        other, other_binding = new_id(), new_id()
        await seed_binding(engine, other, other_binding)
        assert await accept(engine, other, other_binding)
    run("room", case)


def test_366_day_request_and_completed_windows_release_capacity():
    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        annual = SimpleNamespace(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        await accept(engine, owner, binding, annual)
        assert await counts(engine, TABLES) == [1, 1, 53, 1]
        next_year = SimpleNamespace(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        await accept(engine, owner, binding, next_year)
        assert await counts(engine, TABLES) == [2, 2, 106, 2]
        third_year = SimpleNamespace(start_date=date(2023, 1, 1), end_date=date(2023, 12, 31))
        with pytest.raises(ApiError) as full:
            await accept(engine, owner, binding, third_year)
        assert full.value.status == 429
        assert await counts(engine, TABLES) == [2, 2, 106, 2]
        async with engine.begin() as conn:
            await execute(conn, "UPDATE history_sync_windows SET state='succeeded'")
            await execute(conn, "UPDATE history_syncs SET status='succeeded'")
            await execute(conn, "UPDATE room_operations SET state='succeeded'")
        await accept(engine, owner, binding, third_year)
        assert await counts(engine, TABLES) == [3, 3, 159, 3]
    run("room", case)


def test_outbox_failure_rolls_back_all_admission_rows(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("synthetic outbox failure")

    monkeypatch.setattr(history_jobs, "append_event", fail)

    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        with pytest.raises(RuntimeError):
            await accept(engine, owner, binding)
        assert await counts(engine, TABLES) == [0, 0, 0, 0]
    run("room", case)
