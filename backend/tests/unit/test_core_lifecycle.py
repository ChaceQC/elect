"""核心部分启动失败不得留下后台，退出先同时停止各域领取再释放数据库。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.common import business, context
from services.common.background import Role
from services.core import lifecycle
from services.core.app import core_app, domain_health


@pytest.mark.parametrize("fail_at", [None, "monitoring"])
def test_all_contexts_precede_background_and_partial_start_closes_resources(
    runtime_factory, monkeypatch, tmp_path, fail_at,
):
    from services.common import background_roles, heartbeat

    monkeypatch.setenv("ELECT_PROCESS_MODE", "combined")
    monkeypatch.setenv("ELECT_BACKGROUND_ENABLED", "true")
    monkeypatch.setattr(heartbeat, "HEARTBEAT_DIR", tmp_path / "health")
    runtimes = {name: runtime_factory(name) for name in ("gateway", *lifecycle.CORE_DOMAINS)}
    monkeypatch.setattr(lifecycle, "load_runtime", lambda name, **_: runtimes[name])
    opened, started, stopped, disposed = [], [], [], []

    async def initialize(app, name):
        opened.append(name)
        if name == fail_at:
            raise RuntimeError("synthetic initialization failure")

    async def runner(app, stop, beat, hub):
        assert len(opened) == 7
        started.append(app.state.runtime.service)
        beat.write(healthy=True)
        await stop.wait()
        stopped.append(app.state.runtime.service)

    @asynccontextmanager
    async def managed(app, name, **kwargs):
        async def dispose():
            # 正常退出必须先停止全部6个领域，启动失败则不能启动任何后台。
            assert len(stopped) == (6 if fail_at is None else 0)
            disposed.append(name)

        engine = SimpleNamespace(dispose=dispose)
        async with context.domain_context(app, name, **kwargs,
                                          database_factory=lambda _: engine, head=lambda _: "head"):
            yield app

    monkeypatch.setattr(business, "initialize", initialize)
    monkeypatch.setattr(business, "close", AsyncMock())
    monkeypatch.setattr(lifecycle, "domain_context", managed)
    monkeypatch.setattr(background_roles, "roles", lambda _: [Role("synthetic", runner)])

    async def verify():
        app = core_app()
        if fail_at:
            with pytest.raises(RuntimeError, match="synthetic initialization"):
                async with app.router.lifespan_context(app):
                    pytest.fail("partial initialization must fail")
            assert started == []
        else:
            async with app.router.lifespan_context(app):
                assert len(started) == 6
                assert app.state.database is None
                assert all(c.state.background.available() for c in app.state.domains.values())
        assert set(disposed) == set(opened) - {"gateway"}

    asyncio.run(verify())


def test_core_health_fails_on_domain_role_failure(monkeypatch):
    import importlib

    module = importlib.import_module("services.core.app")
    monkeypatch.setattr(module, "database_ready", AsyncMock())
    monkeypatch.setattr(module, "transport_status", AsyncMock(return_value={"redis": True}))
    supervisor = SimpleNamespace(snapshot=lambda: {"worker": {"status": "failed"}},
                                 available=lambda: False)
    app = SimpleNamespace(state=SimpleNamespace(database=object(), migration_head="head",
                                               runtime=object(), background=supervisor))
    assert asyncio.run(domain_health(app))["status"] == "not_ready"
