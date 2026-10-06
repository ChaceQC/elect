import asyncio
from contextlib import asynccontextmanager
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services.common import app as app_module
from services.common import background_roles, business
from services.common import heartbeat as heartbeat_module
from services.common.background import Role, require_standalone, shutdown_timeout, start_background


@pytest.mark.parametrize("service", [
    "identity", "school_adapter", "room", "monitoring", "notification", "payment", "audit",
])
def test_every_domain_api_uses_one_context_and_recovery_disables_all_roles(
    service, runtime_factory, monkeypatch, tmp_path,
):
    runtime_factory(service)
    monkeypatch.setenv("ELECT_PROCESS_MODE", "combined")
    monkeypatch.setenv("ELECT_BACKGROUND_ENABLED", "true")
    monkeypatch.setattr(heartbeat_module, "HEARTBEAT_DIR", tmp_path / "health")
    engine, client = SimpleNamespace(dispose=AsyncMock()), object()
    factory = Mock(return_value=engine)
    monkeypatch.setattr(app_module, "create_database", factory)
    monkeypatch.setattr(app_module, "migration_head", lambda service: "head")
    seen = []
    configured = background_roles.roles(service)

    async def initialized(app, service):
        app.state.service_client = client

    async def runner(app, stop, heartbeat, hub):
        seen.append((app.state.database, app.state.service_client, hub))
        heartbeat.write(healthy=True)
        await stop.wait()

    monkeypatch.setattr(business, "initialize", initialized)
    closing = AsyncMock()
    monkeypatch.setattr(business, "close", closing)
    monkeypatch.setattr(background_roles, "roles", lambda service: [
        Role(role.name, runner, max_age=role.max_age) for role in configured
    ])

    async def verify():
        # 使用生产app模块，Audit也必须接通生命周期，不能只测试工厂的人工参数。
        app = import_module(f"services.{service}.app").app
        async with app.router.lifespan_context(app):
            assert factory.call_count == 1 and len(seen) == len(configured)
            assert all(entry[:2] == (engine, client) for entry in seen)
            assert all(entry[2] is seen[0][2] for entry in seen)
            supervisor = app.state.background
            assert supervisor.shutdown_timeout == shutdown_timeout(service)
            assert supervisor.available()
            with pytest.raises(RuntimeError):
                require_standalone()
            await supervisor.close()
            monkeypatch.setenv("ELECT_BACKGROUND_ENABLED", "false")
            await start_background(app, service)
            assert app.state.background is None
            with pytest.raises(RuntimeError):
                require_standalone()
        closing.assert_awaited_once()
        engine.dispose.assert_awaited_once()

    asyncio.run(verify())


@pytest.mark.parametrize("service,prefix", [("room", "history"), ("payment", "payment")])
def test_disconnected_amqp_channel_cannot_block_persistent_scans(service, prefix, monkeypatch):
    wakeups = import_module(f"services.{service}.wakeups")
    # channel.ready可能无限等待；将整体预算缩短，保留真实取消语义复现该故障。
    monkeypatch.setattr(
        wakeups, "asyncio", SimpleNamespace(timeout=lambda _: asyncio.timeout(0.05)),
    )

    async def verify():
        waiting = asyncio.Event()

        async def get(**kwargs):
            await waiting.wait()

        broker = SimpleNamespace(close=AsyncMock())
        state = SimpleNamespace(**{
            f"{prefix}_broker": broker, f"{prefix}_queue": SimpleNamespace(get=get),
        })
        async with asyncio.timeout(0.5):
            await wakeups.drain(SimpleNamespace(state=state))
        broker.close.assert_awaited_once()
        assert getattr(state, f"{prefix}_broker") is None
        assert getattr(state, f"{prefix}_reconnect_at") > 0

    asyncio.run(verify())


def test_notification_keeps_sending_independent_and_gateway_has_no_background():
    roles = background_roles.roles("notification")
    assert "worker" not in {role.name for role in roles}
    assert background_roles.roles("gateway") == []
    assert shutdown_timeout("payment") >= 170
    assert shutdown_timeout("room") >= 120
    assert shutdown_timeout("monitoring") >= 90


@pytest.mark.parametrize("stopped", [False, True])
def test_old_queue_hints_do_not_starve_sql_but_shutdown_prevents_claims(monkeypatch, stopped):
    from services.monitoring import job, worker

    async def verify():
        stop = asyncio.Event()

        async def hint(*args):
            if stopped:
                stop.set()
            return True  # 已终结或重复提示仍会被ACK，但不代表领取了有效运行。

        tick = AsyncMock(return_value=False)
        monkeypatch.setattr(job, "message_tick", hint)
        monkeypatch.setattr(worker, "worker_tick", tick)
        assert await job.consumer_tick("worker", object(), object(), Mock(), stop)
        assert tick.await_count == (0 if stopped else 1)

    asyncio.run(verify())


def test_room_stop_during_sync_does_not_claim_history(monkeypatch):
    from services.room import query_worker, wakeups, worker

    async def verify():
        stop = asyncio.Event()

        async def controlled(app):
            stop.set()
            return True

        monkeypatch.setattr(worker, "sync_tick", controlled)
        query, drain = AsyncMock(), AsyncMock()
        monkeypatch.setattr(query_worker, "query_tick", query)
        monkeypatch.setattr(wakeups, "drain", drain)
        assert await worker.room_tick(object(), stop=stop)
        query.assert_not_awaited()
        drain.assert_not_awaited()

    asyncio.run(verify())


def test_identity_stop_between_attempts_does_not_start_next_attempt(monkeypatch):
    from services.identity import recovery, revocation

    async def verify():
        stop = asyncio.Event()
        identifiers = [b"1" * 16, b"2" * 16]
        rows = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [
            {"id": identifier} for identifier in identifiers
        ]))
        monkeypatch.setattr(recovery, "execute", AsyncMock(return_value=rows))
        monkeypatch.setattr(revocation, "recover_revocation", AsyncMock(return_value=False))

        @asynccontextmanager
        async def scope(*args, **kwargs):
            yield object()

        async def advance(*args):
            stop.set()

        saga = SimpleNamespace(
            locked=scope, read=AsyncMock(return_value={"state": "activating"}),
            advance=AsyncMock(side_effect=advance),
        )
        app = SimpleNamespace(state=SimpleNamespace(
            database=SimpleNamespace(begin=scope), login_saga=saga,
        ))
        assert await recovery.recover_tick(app, stop=stop)
        saga.advance.assert_awaited_once()
        saga.read.assert_awaited_once()

    asyncio.run(verify())


def test_payment_stop_during_wakeup_does_not_claim_order_and_closes_channel(monkeypatch):
    from services.payment import process, wakeups

    async def verify():
        stop, hub = asyncio.Event(), object()
        broker = SimpleNamespace(close=AsyncMock())
        app = SimpleNamespace(state=SimpleNamespace(payment_broker=broker))

        async def draining(app, **kwargs):
            assert kwargs["hub"] is hub
            stop.set()

        worker = AsyncMock()
        monkeypatch.setattr(wakeups, "drain", draining)
        monkeypatch.setattr(process, "worker_tick", worker)
        await process.role_loop("worker", app, stop, Mock(), hub)
        worker.assert_not_awaited()
        broker.close.assert_awaited_once()
        assert app.state.payment_broker is None

    asyncio.run(verify())
