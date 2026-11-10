import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services.monitoring import job


def test_binding_hint_is_committed_and_acked_without_creating_a_run(monkeypatch):
    async def verify():
        message = SimpleNamespace(ack=AsyncMock(), nack=AsyncMock())
        event, engine = SimpleNamespace(type="room.binding_confirmed"), object()
        monkeypatch.setattr(job, "verified_event", lambda *args: event)
        claim, consume, execute_run = AsyncMock(), AsyncMock(return_value=True), AsyncMock()
        monkeypatch.setattr(job, "claim_run", claim)
        monkeypatch.setattr(job, "consume_once", consume)
        monkeypatch.setattr(job, "execute_run", execute_run)
        assert await job.message_tick(
            SimpleNamespace(state=SimpleNamespace(database=engine, runtime=object())),
            SimpleNamespace(get=AsyncMock(return_value=message)), Mock(), asyncio.Event(),
        )
        consume.assert_awaited_once_with(engine, "room.binding_confirmed", event, job.registered)
        message.ack.assert_awaited_once()
        claim.assert_not_awaited()
        execute_run.assert_not_awaited()

    asyncio.run(verify())


@pytest.mark.parametrize(("enabled", "slots"), [(None, 2), (False, 2), (True, 4)])
def test_worker_slots_share_resources_and_stop_drains_them(monkeypatch, enabled, slots):
    async def verify():
        stop, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        hub, heartbeat = object(), Mock()
        app = object() if enabled is None else SimpleNamespace(
            state=SimpleNamespace(school_proxy_enabled=enabled),
        )
        slot_beats = [Mock() for _ in range(slots)]
        heartbeat.child.side_effect = slot_beats
        running, maximum, calls = 0, 0, []

        async def scan(role, seen_app, seen_stop, seen_heartbeat, seen_hub):
            nonlocal running, maximum
            assert (role, seen_app, seen_stop, seen_hub) == ("worker", app, stop, hub)
            assert seen_heartbeat in slot_beats
            while not stop.is_set():
                calls.append(True)
                running += 1
                maximum = max(maximum, running)
                if running == slots:
                    started.set()
                await release.wait()
                running -= 1

        monkeypatch.setattr(job, "scan_loop", scan)
        worker = asyncio.create_task(job.role_loop("worker", app, stop, heartbeat, hub))
        await asyncio.wait_for(started.wait(), 0.5)
        assert maximum == slots and len(calls) == slots
        stop.set()
        await asyncio.sleep(0)
        assert not worker.done()
        release.set()
        await asyncio.wait_for(worker, 0.5)
        assert running == 0 and len(calls) == slots

    asyncio.run(verify())


@pytest.mark.parametrize("enabled", [None, False, True])
def test_scheduler_receives_proxy_setting(monkeypatch, enabled):
    async def verify():
        stop, engine = asyncio.Event(), object()
        state = SimpleNamespace(database=engine)
        if enabled is not None:
            state.school_proxy_enabled = enabled
        app = SimpleNamespace(state=state)

        async def tick(*args, **kwargs):
            stop.set()
            assert args == (engine,) and kwargs == {"proxy_enabled": bool(enabled)}
            return True

        monkeypatch.setattr(job, "scheduler_tick", tick)
        monkeypatch.setattr(job, "pause", AsyncMock())
        await job.scan_loop("scheduler", app, stop, Mock())

    asyncio.run(verify())


def test_worker_slot_failure_cancels_its_peer_and_fails_the_role(monkeypatch):
    async def verify():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        calls = 0

        async def scan(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                await entered.wait()
                raise RuntimeError("slot failed")
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(job, "scan_loop", scan)
        with pytest.raises(ExceptionGroup):
            await job.role_loop("worker", SimpleNamespace(), asyncio.Event(), Mock(), object())
        assert cancelled.is_set() and len(asyncio.all_tasks()) == 1

    asyncio.run(verify())
