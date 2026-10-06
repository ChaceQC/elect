import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.common import heartbeat as heartbeat_module
from services.common.background_roles import roles
from services.common.heartbeat import Heartbeat
from services.common.ids import new_id
from services.room import removal_saga, worker


def test_room_control_progresses_while_history_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat_module, "HEARTBEAT_DIR", tmp_path / "health")

    async def verify():
        stop, entered, checked, release = (asyncio.Event() for _ in range(4))
        app = SimpleNamespace(state=SimpleNamespace())

        async def slow_history(*args, **kwargs):
            with kwargs["heartbeat"].work(90, lease_seconds=45):
                entered.set()
                await release.wait()
            return True

        async def control(*args):
            await entered.wait()
            checked.set()
            stop.set()
            return True

        history, checker = AsyncMock(side_effect=slow_history), AsyncMock(side_effect=control)
        monkeypatch.setattr(worker, "room_tick", history)
        monkeypatch.setattr(worker, "control_tick", checker)
        active = {role.name: role for role in roles("room")}
        query_beat, control_beat = Heartbeat("room", "worker"), Heartbeat("room", "control")
        assert set(active) == {"relay", "worker", "control"}
        async with asyncio.timeout(1):
            async with asyncio.TaskGroup() as tasks:
                query = tasks.create_task(active["worker"].run(app, stop, query_beat, None))
                tasks.create_task(active["control"].run(app, stop, control_beat, None))
                await checked.wait()
                assert not query.done()
                slots = query_beat.snapshot()["slots"]
                assert len(slots) == 2 and all(value["inflight"] for value in slots.values())
                release.set()
        assert history.await_count == 2
        checker.assert_awaited_once()

    asyncio.run(verify())


@pytest.mark.parametrize("error,delay", [(None, 2), ("SCHOOL_TIMEOUT", 30)])
def test_unknown_removal_polls_original_operation_without_redispatch(monkeypatch, error, delay):
    save = AsyncMock()
    monkeypatch.setattr(removal_saga, "update", save)
    client = SimpleNamespace(call=AsyncMock(return_value={"state": "unknown", "error_code": error}))
    row = {"saga_step": "removal_reconciling", "removal_was_default": False,
           "binding_status": "unknown", "upstream_operation_id": new_id().bytes}
    principal = SimpleNamespace(user_id=new_id(), request_id=new_id())
    asyncio.run(removal_saga.RemovalSaga(object(), client).advance(row, principal))
    assert client.call.await_args.args[1] == "/upstream/operations"
    assert save.await_args.kwargs["delay"] == delay
    assert save.await_args.kwargs["binding_status"] == "unknown"
