import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import uvicorn

from services.common import app as app_module
from services.common import heartbeat as heartbeat_module
from services.common.background import (
    BackgroundSupervisor,
    Role,
    background_enabled,
    require_standalone,
    start_background,
)
from services.common.broker import Broker, BrokerHub
from services.common.heartbeat import Heartbeat, job_healthy
from services.common.server import ManagedServer


@pytest.fixture(autouse=True)
def heartbeat_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat_module, "HEARTBEAT_DIR", tmp_path / "health")


def test_heartbeats_are_independent_and_restarts_do_not_reuse_success():
    scheduler = Heartbeat("monitoring", "scheduler")
    worker = Heartbeat("monitoring", "worker")
    scheduler.write(healthy=True, activity=True)
    worker.write(healthy=True)
    assert scheduler.path != worker.path and job_healthy()
    worker.finish("failed")
    assert scheduler.snapshot()["status"] == "ready" and not job_healthy()
    assert Heartbeat("monitoring", "worker").snapshot()["last_success"] == 0
    scheduler.document["last_tick"] = time.time() - 21
    assert scheduler.snapshot()["status"] == "stale"


async def advancing(app, stop, heartbeat, hub):
    heartbeat.write(healthy=True)
    await stop.wait()


def test_combined_lifespan_shares_context_and_exposes_role_failure(runtime_factory, monkeypatch):
    runtime_factory("monitoring")
    monkeypatch.setenv("ELECT_PROCESS_MODE", "combined")
    engine, client = SimpleNamespace(dispose=AsyncMock()), object()
    factory = Mock(return_value=engine)
    monkeypatch.setattr(app_module, "create_database", factory)
    monkeypatch.setattr(app_module, "migration_head", lambda service: "head")
    monkeypatch.setattr(app_module, "database_ready", AsyncMock())
    monkeypatch.setattr(app_module, "transport_status", AsyncMock(return_value={}))
    from services.common import business
    from services.monitoring import job

    seen = []

    async def initialized(app, service):
        app.state.service_client = client

    async def runner(app, stop, heartbeat, hub):
        seen.append((app.state.database, app.state.service_client, hub))
        await advancing(app, stop, heartbeat, hub)

    closing = AsyncMock()
    monkeypatch.setattr(business, "initialize", initialized)
    monkeypatch.setattr(business, "close", closing)
    monkeypatch.setattr(job, "roles", lambda: [Role("scheduler", runner), Role("worker", runner)])

    async def verify():
        app = app_module.create_app("monitoring", business=True)
        async with app.router.lifespan_context(app):
            assert factory.call_count == 1
            assert len(seen) == 2 and all(entry[:2] == (engine, client) for entry in seen)
            assert seen[0][2] is seen[1][2]
            supervisor = app.state.background
            with pytest.raises(RuntimeError):
                await supervisor.start()
            with pytest.raises(RuntimeError):
                await start_background(app, "monitoring")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://monitoring"
            ) as browser:
                response = await browser.get("/health/ready")
                assert response.status_code == 200 and response.json()["status"] == "ready"
                supervisor.heartbeats["worker"].write(healthy=False)
                response = await browser.get("/health/ready")
                assert response.status_code == 200 and response.json()["status"] == "degraded"
                supervisor.tasks["worker"].cancel()
                await asyncio.gather(supervisor.tasks["worker"], return_exceptions=True)
                response = await browser.get("/health/ready")
                assert response.status_code == 503
                assert response.json()["background_roles"]["worker"]["status"] == "failed"
                assert not supervisor.tasks["scheduler"].done()
                assert (await browser.get("/health/live")).status_code == 200
        closing.assert_awaited_once()
        engine.dispose.assert_awaited_once()

    asyncio.run(verify())


@pytest.mark.parametrize("failure", ["return", "raise", "stale"])
def test_required_roles_cannot_silently_stop_or_stall(failure):
    async def runner(app, stop, heartbeat, hub):
        heartbeat.write(healthy=True)
        if failure == "raise":
            raise RuntimeError("sensitive-error-not-logged")
        if failure == "return":
            return
        heartbeat.document["last_tick"] = time.time() - 21
        await stop.wait()

    async def verify():
        app = SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(service="monitoring")))
        supervisor = BackgroundSupervisor(app, [Role("worker", runner)])
        await supervisor.start()
        assert not supervisor.available()
        assert supervisor.snapshot()["worker"]["status"] == (
            "stale" if failure == "stale" else "failed"
        )
        await supervisor.close()

    asyncio.run(verify())


@pytest.mark.parametrize("drain", [True, False])
def test_shutdown_stops_claiming_then_drains_or_cancels_inflight(drain):
    async def verify():
        app = SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(service="monitoring")))
        entered, release = asyncio.Event(), asyncio.Event()
        claims, cancelled = [], []

        async def runner(app, stop, heartbeat, hub):
            while not stop.is_set():
                claims.append(1)
                heartbeat.write(healthy=True)
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.append(True)
                    raise

        supervisor = BackgroundSupervisor(app, [Role("worker", runner)], shutdown_timeout=0.05)
        await supervisor.start()
        await entered.wait()
        supervisor.request_stop()
        closing = asyncio.create_task(supervisor.close())
        await asyncio.sleep(0)
        assert not closing.done() and supervisor.stop.is_set()
        if drain:
            release.set()
        await closing
        assert len(claims) == 1 and bool(cancelled) != drain
        assert supervisor.snapshot()["worker"]["status"] == "stopped"
        assert all(task.done() for task in supervisor.tasks.values())

    asyncio.run(verify())


def test_background_disable_overrides_combined_and_blocks_independent_entry(monkeypatch):
    from services.common.background import start_background

    monkeypatch.setenv("ELECT_PROCESS_MODE", "combined")
    monkeypatch.setenv("ELECT_BACKGROUND_ENABLED", "false")
    app = SimpleNamespace(state=SimpleNamespace())
    asyncio.run(start_background(app, "monitoring"))
    assert app.state.background is None
    with pytest.raises(RuntimeError):
        require_standalone()
    monkeypatch.setenv("ELECT_BACKGROUND_ENABLED", "true")
    with pytest.raises(RuntimeError):
        require_standalone()
    monkeypatch.setenv("ELECT_BACKGROUND_ENABLED", "yes")
    with pytest.raises(RuntimeError):
        background_enabled()


def test_signal_requests_background_stop_before_http_shutdown():
    supervisor = SimpleNamespace(request_stop=Mock())
    app = SimpleNamespace(state=SimpleNamespace(background=supervisor))
    server = ManagedServer(uvicorn.Config(app=app), app)
    server.handle_exit(15, None)
    supervisor.request_stop.assert_called_once()
    assert server.should_exit


def test_amqp_connection_is_shared_but_channels_are_independent(monkeypatch):
    from services.common import broker as broker_module

    async def verify():
        channels = [AsyncMock(), AsyncMock()]
        connection = SimpleNamespace(
            is_closed=False, close=AsyncMock(), channel=AsyncMock(side_effect=channels)
        )
        connect = AsyncMock(return_value=connection)
        monkeypatch.setattr(broker_module.aio_pika, "connect_robust", connect)
        runtime = SimpleNamespace(amqp_url=SimpleNamespace(get_secret_value=lambda: "synthetic"))
        hub = BrokerHub(runtime)
        publisher, consumer = Broker(runtime, hub=hub), Broker(runtime, hub=hub)
        await asyncio.gather(publisher.open(), consumer.open())
        assert connect.await_count == 1 and publisher.channel is not consumer.channel
        assert all(call.kwargs["publisher_confirms"] for call in connection.channel.await_args_list)
        await consumer.close()
        connection.close.assert_not_awaited()
        await publisher.close()
        await hub.close()
        connection.close.assert_awaited_once()

    asyncio.run(verify())
