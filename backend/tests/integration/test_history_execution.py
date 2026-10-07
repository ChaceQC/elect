"""R2窗口续租、超时接管及批量原子提交，使用生产2+1池。"""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from query_resource_support import database, requires_mysql, seed_binding
from sqlalchemy.exc import DataError
from test_history_admission import accept

from services.common.ids import new_id
from services.common.sql import execute, first
from services.room import history_execution as execution
from services.room.history_jobs import claim_history
from services.room.history_store import finish_history
from services.room.preference_store import lock_preference

pytestmark = requires_mysql
EMPTY = {"items": [], "request_room_id": "synthetic"}


async def setup(engine):
    owner, binding = new_id(), new_id()
    await seed_binding(engine, owner, binding)
    await accept(engine, owner, binding)
    return owner, binding, await claim_history(engine)


async def window(engine, row):
    async with engine.connect() as conn:
        return await first(conn, "SELECT * FROM history_sync_windows WHERE id=:id", id=row["id"])


def run(case, monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")
    monkeypatch.setattr(execution, "LEASE_SECONDS", 1)
    monkeypatch.setattr(execution, "RENEW_SECONDS", .05)
    monkeypatch.setattr(execution, "EXECUTION_SECONDS", 3)

    async def scenario():
        async with database("room", production_pool=True) as engine:
            await case(engine)
    asyncio.run(scenario())


def test_renew_covers_school_and_commit_lock_wait(monkeypatch):
    async def case(engine):
        owner, _, row = await setup(engine)
        initial_lease = (await window(engine, row))["lease_until"]
        entered, release = asyncio.Event(), asyncio.Event()
        renewed = asyncio.Event()
        original = execution.renew

        async def renew(*args):
            result = await original(*args)
            renewed.set()
            return result

        monkeypatch.setattr(execution, "renew", renew)

        async def call(*args, **kwargs):
            assert kwargs["budget"] <= execution.EXECUTION_SECONDS
            entered.set()
            await release.wait()
            return EMPTY

        app = SimpleNamespace(state=SimpleNamespace(
            database=engine, service_client=SimpleNamespace(call=call)))
        task = asyncio.create_task(execution.execute_window(app, row))
        await entered.wait()
        await renewed.wait()
        assert (await window(engine, row))["lease_until"] > initial_lease
        async with engine.begin() as conn:
            await lock_preference(conn, owner)
            renewed.clear()
            release.set()
            await renewed.wait()  # 提交等owner锁时仍能用第3条连接续租。
            assert not task.done()
        assert await task
        assert (await window(engine, row))["state"] == "succeeded"
    run(case, monkeypatch)


def test_lost_lease_cancels_wait_and_old_epoch_cannot_commit(monkeypatch):
    async def case(engine):
        _, _, row = await setup(engine)
        entered, cancelled = asyncio.Event(), asyncio.Event()

        async def call(*args, **kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        app = SimpleNamespace(state=SimpleNamespace(
            database=engine, service_client=SimpleNamespace(call=call)))
        task = asyncio.create_task(execution.execute_window(app, row))
        await entered.wait()
        async with engine.begin() as conn:
            await execute(conn, "UPDATE history_sync_windows SET lease_until=UTC_TIMESTAMP(6) "
                          "WHERE id=:id", id=row["id"])
        replacement = await claim_history(engine)
        assert replacement["execution_epoch"] > row["execution_epoch"]
        assert not await task and cancelled.is_set()
        assert not await finish_history(engine, row, EMPTY, None)
        assert await finish_history(engine, replacement, EMPTY, None)
    run(case, monkeypatch)


def test_deadline_expiry_recovers_and_stops_after_three_attempts(monkeypatch):
    async def case(engine):
        monkeypatch.setattr(execution, "EXECUTION_SECONDS", .12)
        _, _, row = await setup(engine)

        async def call(*args, **kwargs):
            await asyncio.Event().wait()

        app = SimpleNamespace(state=SimpleNamespace(
            database=engine, service_client=SimpleNamespace(call=call)))
        for attempt in range(1, 4):
            assert row["attempt_count"] == attempt
            assert not await execution.execute_window(app, row)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE history_sync_windows SET lease_until=UTC_TIMESTAMP(6) "
                              "WHERE id=:id", id=row["id"])
            previous, row = row, await claim_history(engine)
        assert row is None and (await window(engine, previous))["state"] == "failed"
    run(case, monkeypatch)


def test_large_window_is_atomic_and_repeated_rows_are_preserved(monkeypatch):
    async def case(engine):
        owner, binding, row = await setup(engine)
        record = {"row_hash": "00" * 32, "record_date": date(2026, 9, 1),
                  "last_reading": None, "reading": None, "energy_usage": None,
                  "charged_amount": None, "charge_status": None, "quality": "partial"}
        assert await finish_history(engine, row,
                                    {**EMPTY, "items": [record] * 10000}, None)
        await accept(engine, owner, binding)
        newer = await claim_history(engine)
        original = execution.finish_history

        async def bad_commit(engine, row, value, *args, **kwargs):
            value["items"][300] = {**record, "quality": "x" * 100}
            return await original(engine, row, value, *args, **kwargs)

        monkeypatch.setattr(execution, "finish_history", bad_commit)

        async def call(*args, **kwargs):
            return {**EMPTY, "items": [record] * 500}

        app = SimpleNamespace(state=SimpleNamespace(
            database=engine, service_client=SimpleNamespace(call=call)))
        with pytest.raises(DataError):
            await execution.execute_window(app, newer)
        async with engine.connect() as conn:
            actual = await first(conn, "SELECT COUNT(*) AS n,MAX(occurrence_index) AS last "
                                 "FROM school_history_records WHERE binding_id=:id",
                                 id=binding.bytes)
        assert actual["n"] == actual["last"] == 10000
    run(case, monkeypatch)
