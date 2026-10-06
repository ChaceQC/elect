"""实际MySQL/Saga/恢复循环/健康/监督判定；可控时钟与合成下游，无外发。"""

import asyncio
import secrets
from functools import partial
from types import SimpleNamespace
from uuid import UUID

import pytest
from login_resource_support import Client, command
from query_resource_support import database, requires_mysql

from services.common import business_worker, health_state, heartbeat
from services.common.background import BackgroundSupervisor, Role
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.process_control import ProcessControl
from services.common.sql import execute, first
from services.identity import recovery
from services.identity.application.login import LoginSaga
from services.identity.sessions import AppSessions

pytestmark = requires_mysql


class FaultClient(Client):
    def __init__(self):
        super().__init__()
        self.release.set()
        self.error = None
        self.failures = 0
        self.inspect = None

    async def call(self, service, path, scope, request_id, payload, **kwargs):
        if self.inspect:
            await self.inspect()
        if self.error:
            self.failures += 1
            raise self.error
        if path.endswith("-revoke") or path == "/credentials/revoke":
            return {}
        return await super().call(service, path, scope, request_id, payload, **kwargs)


@pytest.fixture
def clock(monkeypatch, tmp_path):
    value = SimpleNamespace(mono=100.0)
    timer = SimpleNamespace(monotonic=lambda: value.mono, time=lambda: value.mono + 1000)
    monkeypatch.setattr(heartbeat, "time", timer)
    monkeypatch.setattr(health_state, "time", timer)
    monkeypatch.setattr(heartbeat, "HEARTBEAT_DIR", tmp_path / "health")
    return value


async def seed(engine, *, state="activating", revoke=False):
    client = FaultClient()
    saga = LoginSaga(engine, client, AppSessions(engine, secrets.token_bytes(32)))
    row = await saga.attempt(command(), secrets.token_hex(32), None)
    row = await saga.advance(row, new_id())
    async with engine.begin() as conn:
        if revoke:
            await execute(conn, "INSERT INTO credential_operations "
                          "(id,owner_user_id,credential_ref,expected_credential_version,state,"
                          "saga_step,next_reconcile_at) VALUES (:id,:owner,:ref,1,'accepted',"
                          "'accepted',UTC_TIMESTAMP(6))", id=row["id"],
                          owner=row["user_id"], ref=row["credential_ref"])
        else:
            await execute(conn, "UPDATE login_attempts SET state=:state,"
                          "updated_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 10 SECOND),"
                          "next_reconcile_at=UTC_TIMESTAMP(6) WHERE id=:id",
                          state=state, id=row["id"])
        await execute(conn, "UPDATE users SET credential_operation_id=:attempt WHERE id=:owner",
                      attempt=row["id"], owner=row["user_id"])
    app = SimpleNamespace(state=SimpleNamespace(
        database=engine, login_saga=saga, service_client=client,
        runtime=SimpleNamespace(service="identity"),
    ))
    return app, client, row


async def elapse(engine):
    # 推进持久到期时间，保留生产5秒退避中的未到期扫描，不实际等待60秒。
    async with engine.begin() as conn:
        for table in ("login_attempts", "credential_operations"):
            await execute(conn, f"UPDATE {table} SET "
                          "next_reconcile_at=DATE_SUB(next_reconcile_at,INTERVAL 1 SECOND),"
                          "updated_at=DATE_SUB(updated_at,INTERVAL 1 SECOND)")


async def run_loop(app, clock, monkeypatch, *, recover_at=None, busy=False):
    control = ProcessControl("identity", 125)
    control.loop, control.stop = asyncio.get_running_loop(), asyncio.Event()
    app.state.process_control = control
    supervisor = BackgroundSupervisor(app, [Role(
        "recovery", partial(business_worker.business_loop, "identity"),
    )], shutdown_timeout=125)
    snapshots = []

    async def pause(stop, delay):
        assert delay == 1
        snapshots.append(supervisor.snapshot()["recovery"])
        control._check_health([supervisor], [])
        if len(snapshots) >= 71:
            supervisor.request_stop()
        if recover_at == len(snapshots):
            app.state.service_client.error = None
        clock.mono += 1
        await elapse(app.state.database)

    monkeypatch.setattr(business_worker, "pause", pause)
    try:
        if busy:
            async with app.state.login_saga.gate.enter():
                await supervisor.start()
                await supervisor.tasks["recovery"]
        else:
            await supervisor.start()
            await supervisor.tasks["recovery"]
    finally:
        await supervisor.close()
        control.finish()
    return snapshots, control


@pytest.mark.parametrize("state,revoke", [
    ("identity_committed", False), ("activating", False), ("activated", True),
])
def test_dependency_failure_survives_retry_gaps_and_reaches_fatal(
    monkeypatch, clock, state, revoke,
):
    async def case():
        async with database("identity", production_pool=True) as engine:
            app, client, row = await seed(engine, state=state, revoke=revoke)
            client.error = ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic", True)
            snapshots, control = await run_loop(app, clock, monkeypatch)
            assert len(snapshots) == 61
            assert all(s["success_monotonic"] is None for s in snapshots)
            assert all(s["failure_since_monotonic"] == 100 for s in snapshots)
            assert snapshots[-1]["reason"] == "BUSINESS_FAILURE_BUDGET"
            assert 1 < client.failures < len(snapshots)  # 确实包含未到期扫描。
            assert control.failure == {"domain": "identity", "role": "recovery",
                                       "error_code": "BUSINESS_FAILURE_BUDGET"}
            assert control.stop.is_set()
            table = "credential_operations" if revoke else "login_attempts"
            async with engine.connect() as conn:
                current = await first(conn, f"SELECT state,error_code FROM {table} WHERE id=:id",
                                      id=row["id"])
            assert current["state"] == ("reconciling" if revoke else "activating")
            assert current["error_code"] == ErrorCode.DEPENDENCY_UNAVAILABLE
            assert engine.pool.checkedout() == 0
    asyncio.run(case())


@pytest.mark.parametrize("revoke", [False, True])
def test_transient_failure_recovers_only_after_real_completion(monkeypatch, clock, revoke):
    async def case():
        async with database("identity", production_pool=True) as engine:
            app, client, _ = await seed(engine, revoke=revoke)
            client.error = ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic", True)
            snapshots, control = await run_loop(app, clock, monkeypatch, recover_at=12)
            assert control.failure is None
            assert snapshots[11]["consecutive_failures"] == 12
            assert snapshots[-1]["status"] == "ready"
            assert snapshots[-1]["failure_since_monotonic"] is None
            assert snapshots[-1]["processed"] == 1
    asyncio.run(case())


@pytest.mark.parametrize("revoke", [False, True])
def test_local_gate_busy_is_healthy_without_activity(monkeypatch, clock, revoke):
    async def case():
        async with database("identity", production_pool=True) as engine:
            app, client, _ = await seed(engine, revoke=revoke)
            snapshots, control = await run_loop(app, clock, monkeypatch, busy=True)
            assert control.failure is None and client.failures == 0
            assert all(s["status"] == "ready" and s["processed"] == 0 for s in snapshots)
            assert all(s["failures"] == 0 for s in snapshots)
    asyncio.run(case())


@pytest.mark.parametrize("status,code", [(429, ErrorCode.RATE_LIMITED),
                                        (404, ErrorCode.NOT_FOUND)])
def test_downstream_error_is_not_local_contention_or_success(monkeypatch, clock, status, code):
    async def case():
        async with database("identity", production_pool=True) as engine:
            app, client, _ = await seed(engine)
            client.error = ApiError(status, code, "synthetic", True)
            snapshots, control = await run_loop(app, clock, monkeypatch)
            assert control.failure["error_code"] == "BUSINESS_FAILURE_BUDGET"
            assert snapshots[-1]["success_monotonic"] is None
    asyncio.run(case())


def test_other_success_and_foreground_retry_cannot_clear_pending_failure():
    async def case():
        async with database("identity", production_pool=True) as engine:
            app, client, failed = await seed(engine)
            client.error = ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic", True)
            with pytest.raises(ApiError):
                await recovery.recover_tick(app)
            async with app.state.login_saga.gate.enter():
                with pytest.raises(ApiError):
                    await recovery.recover_tick(app)
            other_app, _, _ = await seed(engine, revoke=True)
            with pytest.raises(ApiError):
                await recovery.recover_tick(other_app)  # 撤回已成功，但失败登录仍在等待。
            async def inspect():
                with pytest.raises(ApiError):
                    await recovery.require_healthy_recovery(app)
            client.inspect = inspect
            with pytest.raises(ApiError):
                await app.state.login_saga.advance(
                    await app.state.login_saga.read(UUID(bytes=failed["id"])), new_id(),
                )  # activating状态写入不能清掉上一轮错误。
    asyncio.run(case())


def test_rejected_precommit_attempt_finishes_without_poisoning_health():
    async def case():
        async with database("identity", production_pool=True) as engine:
            app, client, row = await seed(engine, state="authenticating")
            client.error = ApiError(422, ErrorCode.INVALID_ARGUMENT, "synthetic")
            assert await recovery.recover_tick(app)
            current = await app.state.login_saga.read(UUID(bytes=row["id"]))
            assert current["state"] == "failed"
            await recovery.require_healthy_recovery(app)
            assert not await recovery.recover_tick(app)
    asyncio.run(case())
