"""支付回查角色调度；与MySQL集成用例使用不同模块名，避免pytest收集冲突。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.common import heartbeat as heartbeat_module
from services.common.background_roles import roles
from services.common.heartbeat import Heartbeat
from services.payment import process, wakeups


def test_payment_reconciliation_continues_while_qr_is_blocked_and_drains_on_stop(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(heartbeat_module, "HEARTBEAT_DIR", tmp_path / "health")

    async def verify():
        stop, entered, checked, release = (asyncio.Event() for _ in range(4))
        app = SimpleNamespace(state=SimpleNamespace())

        async def slow_qr(*args, **kwargs):
            entered.set()
            await release.wait()
            return True

        checking = []

        async def check(app, heartbeat, **kwargs):
            assert kwargs["stop"] is stop
            await entered.wait()
            with heartbeat.work(1, lease_seconds=1):
                checking.append(heartbeat)
                if len(checking) == 2:
                    checked.set()
                    stop.set()
                await checked.wait()
            return True

        monkeypatch.setattr(wakeups, "drain", AsyncMock())
        worker, checker = AsyncMock(side_effect=slow_qr), AsyncMock(side_effect=check)
        monkeypatch.setattr(process, "worker_tick", worker)
        monkeypatch.setattr(process, "check_tick", checker)
        active = {role.name: role for role in roles("payment")}
        beat = Heartbeat("payment", "reconciliation")
        assert set(active) == {"relay", "worker", "reconciliation", "recovery"}
        async with asyncio.timeout(1):
            async with asyncio.TaskGroup() as tasks:
                qr = tasks.create_task(active["worker"].run(
                    app, stop, Heartbeat("payment", "worker"), None))
                tasks.create_task(active["reconciliation"].run(app, stop, beat, None))
                await checked.wait()
                assert not qr.done()
                release.set()
        worker.assert_awaited_once()
        assert checker.await_count == 2 and checking[0] is not checking[1]
        assert len(beat.snapshot()["slots"]) == 2

    asyncio.run(verify())
