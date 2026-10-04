"""支付回查角色调度；与MySQL集成用例使用不同模块名，避免pytest收集冲突。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from services.common.background_roles import roles
from services.payment import process, wakeups


def test_payment_reconciliation_continues_while_qr_is_blocked_and_drains_on_stop(monkeypatch):
    async def verify():
        stop, entered, checked, release = (asyncio.Event() for _ in range(4))
        app = SimpleNamespace(state=SimpleNamespace())

        async def slow_qr(*args, **kwargs):
            entered.set()
            await release.wait()
            return True

        async def check(*args):
            await entered.wait()
            checked.set()
            stop.set()
            return True

        monkeypatch.setattr(wakeups, "drain", AsyncMock())
        worker, checker = AsyncMock(side_effect=slow_qr), AsyncMock(side_effect=check)
        monkeypatch.setattr(process, "worker_tick", worker)
        monkeypatch.setattr(process, "check_tick", checker)
        active = {role.name: role for role in roles("payment")}
        assert set(active) == {"relay", "worker", "reconciliation", "recovery"}
        async with asyncio.timeout(1):
            async with asyncio.TaskGroup() as tasks:
                qr = tasks.create_task(active["worker"].run(app, stop, Mock(), None))
                tasks.create_task(active["reconciliation"].run(app, stop, Mock(), None))
                await checked.wait()
                assert not qr.done()
                release.set()
        worker.assert_awaited_once()
        checker.assert_awaited_once()

    asyncio.run(verify())
