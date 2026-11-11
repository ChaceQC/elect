import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.monitoring import scheduler
from services.monitoring.scheduler import latest_slot


def test_missed_slots_only_schedule_latest_and_keep_anchor():
    anchor = datetime(2026, 10, 1, 0, 7, 23)
    slot, following = latest_slot(anchor, anchor + timedelta(hours=5, minutes=20), 75)
    assert slot == anchor + timedelta(hours=5)
    assert following == anchor + timedelta(hours=6, minutes=15)


def test_exact_due_slot_and_initial_enable():
    anchor = datetime(2026, 10, 1)
    assert latest_slot(anchor, anchor, 60) == (anchor, anchor + timedelta(hours=1))
    assert latest_slot(anchor, anchor + timedelta(hours=1), 60) == (
        anchor + timedelta(hours=1),
        anchor + timedelta(hours=2),
    )


@pytest.mark.parametrize("proxy_enabled", [False, True])
@pytest.mark.parametrize(
    ("now", "quiet"),
    [
        (datetime(2026, 1, 1, 14, 59, 59), False),  # 上海 22:59:59
        (datetime(2026, 1, 1, 15), True),  # 上海 23:00
        (datetime(2026, 1, 1, 21, 59, 59), True),  # 次日上海 05:59:59
        (datetime(2026, 1, 1, 22), False),  # 次日上海 06:00
    ],
)
def test_scheduler_quiet_hours(monkeypatch, now, quiet, proxy_enabled):
    anchor = datetime(2026, 1, 1, 14, 15)
    monitor = {
        "id": b"monitor", "schedule_anchor_at": anchor,
        "next_run_at": anchor, "interval_minutes": 60,
    }

    @asynccontextmanager
    async def begin():
        yield object()

    async def read_first(conn, statement, **params):
        if statement == "SELECT UTC_TIMESTAMP(6) AS now":
            return {"now": now}
        if "FROM outbox_events" in statement:
            return None
        assert proxy_enabled and "FOR UPDATE SKIP LOCKED" in statement
        return monitor

    async def run_sql(conn, statement, **params):
        if statement.startswith("SELECT"):
            rows = [] if proxy_enabled else [monitor]
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))

    first = AsyncMock(side_effect=read_first)
    execute = AsyncMock(side_effect=run_sql)
    create = AsyncMock(return_value={"id": b"run"})
    wake = AsyncMock()
    monkeypatch.setattr(scheduler, "first", first)
    monkeypatch.setattr(scheduler, "execute", execute)
    monkeypatch.setattr(scheduler, "create_run", create)
    monkeypatch.setattr(scheduler, "wake", wake)

    assert asyncio.run(scheduler.scheduler_tick(
        SimpleNamespace(begin=begin), proxy_enabled=proxy_enabled
    )) is not quiet
    if quiet:
        assert first.await_count == 1
        execute.assert_not_awaited()
        create.assert_not_awaited()
        wake.assert_not_awaited()
        return

    create.assert_awaited_once()
    if now.hour == 22:
        expected_slot = datetime(2026, 1, 1, 22 if proxy_enabled else 21, 15)
    else:
        expected_slot = anchor
    assert create.await_args.args[2] == expected_slot
    update = execute.await_args_list[-1]
    assert "UPDATE monitors" in update.args[1]
    assert update.kwargs["anchor"] == anchor
    assert update.kwargs["next"] == expected_slot + timedelta(hours=1)
