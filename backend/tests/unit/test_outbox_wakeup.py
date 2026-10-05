import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from services.common.database import OUTBOX_PENDING, create_database
from services.common.outbox import append_event
from services.common.scheduling import IdleBackoff, Wakeup, retry_delay


@pytest.mark.parametrize("outcome", ["commit", "rollback", "commit_failure", "cancel"])
def test_outbox_signal_occurs_after_successful_commit_only(monkeypatch, outcome):
    async def verify():
        engine = create_database("mysql+asyncmy://app:synthetic@mysql/elect_room")
        connection = SimpleNamespace(info={}, execute=AsyncMock())
        committing, committed = asyncio.Event(), asyncio.Event()

        @asynccontextmanager
        async def begin(*args):
            yield connection
            committing.set()
            assert not engine.outbox_wakeup.event.is_set()
            await asyncio.sleep(0)  # COMMIT是异步操作，不能通过call_soon提前唤醒。
            if outcome == "commit_failure":
                raise RuntimeError("commit failed")
            committed.set()

        monkeypatch.setattr(AsyncEngine, "begin", begin)
        event = SimpleNamespace(
            event_id=SimpleNamespace(bytes=b"1" * 16), type="audit.recorded", schema_version=1,
            aggregate_id=SimpleNamespace(bytes=b"2" * 16), aggregate_version=1,
            model_dump_json=lambda: "{}",
        )
        try:
            async with engine.begin() as conn:
                await append_event(conn, event)
                await append_event(conn, event)
                assert not engine.outbox_wakeup.event.is_set()
                if outcome == "rollback":
                    raise ValueError("rollback")
                if outcome == "cancel":
                    raise asyncio.CancelledError()
        except (ValueError, RuntimeError, asyncio.CancelledError):
            assert outcome != "commit"
        assert committed.is_set() == (outcome == "commit")
        assert engine.outbox_wakeup.event.is_set() == committed.is_set()
        assert OUTBOX_PENDING not in connection.info
        # 池中同一连接的下一次空事务不能复用旧提示。
        engine.outbox_wakeup.event.clear()
        if outcome != "commit_failure":
            async with engine.begin():
                pass
            assert not engine.outbox_wakeup.event.is_set()
        await engine.dispose()

    asyncio.run(verify())


def test_idle_backoff_caps_resets_and_fault_retries_have_bounded_jitter():
    idle = IdleBackoff()
    assert [idle.next() for _ in range(6)] == [1, 2, 5, 10, 10, 10]
    assert idle.next(True) == 0 and idle.next() == 1
    assert all(30 <= retry_delay(20) <= 31 for _ in range(20))


def test_wakeup_is_retained_between_scan_and_wait_and_shutdown_cleans_waiters():
    async def verify():
        signal, stop = Wakeup(), asyncio.Event()
        signal.set()
        signal.set()  # 提示合并，实际事件仍在数据库。
        assert await signal.wait(stop, 10)
        assert not signal.event.is_set()
        assert not await signal.wait(stop, 0.01)
        waiting = asyncio.create_task(signal.wait(stop, 10))
        await asyncio.sleep(0)
        stop.set()
        assert not await asyncio.wait_for(waiting, 0.1)
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(verify())
