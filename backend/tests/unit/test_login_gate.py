"""前台队列严格有界，取消/异常/超时均归还执行门。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from services.common.http import ApiError
from services.identity.application.login_gate import LoginGate


def test_bounded_waiters_timeout_cancel_and_handoff():
    async def case():
        gate = LoginGate()

        async def enter():
            async with gate.enter():
                return "entered"

        async with gate.enter():
            first = asyncio.create_task(enter())
            second = asyncio.create_task(enter())
            await asyncio.sleep(0)  # 让两个请求到达执行门的确定同步点。
            assert gate.waiters == 2
            with pytest.raises(ApiError) as full:
                await enter()
            assert full.value.status == 429
            with pytest.raises(ApiError):
                async with gate.enter(background=True):
                    pytest.fail("后台不能排队")
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert gate.waiters == 1
            with pytest.raises(ApiError) as timeout:
                await second
            assert timeout.value.retry_after_seconds == 3
            assert gate.waiters == 0
            waiting = asyncio.create_task(enter())
            await asyncio.sleep(0)
        assert await waiting == "entered"
        with pytest.raises(RuntimeError):
            async with gate.enter():
                raise RuntimeError("synthetic")
        assert await enter() == "entered"
        assert not gate.lock.locked() and gate.waiters == 0
    asyncio.run(case())


def test_revocation_gate_contention_skips_recovery_tick(monkeypatch):
    from services.identity import recovery, revocation
    from services.identity.application.login_gate import busy

    async def unavailable(app):
        raise busy()

    monkeypatch.setattr(revocation, "recover_revocation", unavailable)
    monkeypatch.setattr(recovery, "require_healthy_recovery", AsyncMock())
    assert asyncio.run(recovery.recover_tick(object())) is False
