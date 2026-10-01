"""T3 第一批：真实 MySQL 控制事务/竞态与合成浏览器权限验收。"""

import asyncio
import os
from pathlib import Path
from uuid import UUID

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t3_control_alerts import verify_alert_boundary
from scripts.t3_control_compensation import verify_compensation, verify_transaction_rollback
from scripts.t3_control_fixtures import assert_no_sample, invalid_executions, running, write_sample
from scripts.t3_control_protocol import (
    verify_credential_update,
    verify_proof_api,
    verify_result_race,
)
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import CommitRetarget, PrepareRetarget, RevokeBarrier
from services.common.sql import execute, first
from services.monitoring.barriers import RetargetControls
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.credentials import CredentialControls
from services.monitoring.dto import MonitorPatch
from services.monitoring.fences import fenced_transaction
from services.monitoring.runs import cancel_run


async def rejected_sample(engine, execution, owner):
    try:
        async with fenced_transaction(engine, execution) as (conn, _, _):
            await write_sample(conn, execution, owner)
    except ApiError as error:
        assert error.status == 409
    else:
        raise AssertionError("失效执行越过提交屏障")
    await assert_no_sample(engine, execution.run_id)


async def verify_fences(engine, crypto):
    config = MonitorConfiguration(engine, crypto)
    for mode in ["disable", "cancel", "retarget", "revoke", "lease"]:
        owner = new_id()
        execution, credential = await running(engine, owner)
        for invalid in invalid_executions(execution):
            await rejected_sample(engine, invalid, owner)
        if mode == "disable":
            view = await config.patch(
                owner, MonitorPatch(expected_version=1, enabled=False), new_id()
            )
            assert view.state == "disabled" and view.cancel_pending and view.in_flight_count == 1
            assert view.current_run.state == "cancel_requested"
        elif mode == "cancel":
            view = await cancel_run(engine, owner, execution.run_id, 1, new_id())
            assert view.cancel_pending and view.version == 2
            monitor = await config.get(owner)
            assert monitor.config.enabled and monitor.next_run_at is not None
        elif mode == "retarget":
            await RetargetControls(engine).prepare(
                PrepareRetarget(
                    owner_user_id=owner,
                    request_id=new_id(),
                    operation_id=new_id(),
                    target_binding_id=new_id(),
                    expected_preference_version=1,
                )
            )
        elif mode == "revoke":
            command = RevokeBarrier(
                owner_user_id=owner,
                request_id=new_id(),
                operation_id=new_id(),
                credential_ref=credential,
                expected_credential_version=1,
            )
            control = CredentialControls(engine)
            first_result = await control.prepare(command, revoke=True)
            assert await control.prepare(command, revoke=True) == first_result
            assert not (await config.get(owner)).config.enabled
        else:
            async with engine.begin() as conn:
                await execute(
                    conn,
                    "UPDATE monitor_runs SET lease_until=DATE_SUB(UTC_TIMESTAMP(6),"
                    "INTERVAL 1 SECOND) WHERE id=:id",
                    id=execution.run_id.bytes,
                )
        await rejected_sample(engine, execution, owner)
    # 正向检查同一个 guard 确实允许有效执行写入，而非无条件拒绝。
    owner = new_id()
    execution, _ = await running(engine, owner)
    async with fenced_transaction(engine, execution) as (conn, _, _):
        await write_sample(conn, execution, owner)
        await execute(
            conn,
            "UPDATE monitor_runs SET state='succeeded' WHERE id=:id",
            id=execution.run_id.bytes,
        )
    finished = await cancel_run(engine, owner, execution.run_id, 1, new_id())
    assert finished.state == "succeeded"
    print("关闭/取消/切换/撤权/过期租约阻断迟到样本，有效事务仍可提交：通过")


async def verify_retarget(engine, crypto):
    owner, target, operation = new_id(), new_id(), new_id()
    control, config = RetargetControls(engine), MonitorConfiguration(engine, crypto)
    command = PrepareRetarget(
        owner_user_id=owner,
        request_id=new_id(),
        operation_id=operation,
        target_binding_id=target,
        expected_preference_version=1,
    )
    a, b = await asyncio.gather(control.prepare(command), control.prepare(command))
    assert a == b and a["generation"] == 2
    before = await config.get(owner)
    assert not before.config.enabled and before.state == "retargeting"
    bad = command.model_copy(update={"target_binding_id": new_id()})
    try:
        await control.prepare(bad)
    except ApiError as error:
        assert error.status == 409
    else:
        raise AssertionError("同操作改目标未被拒绝")
    commit = CommitRetarget(
        owner_user_id=owner,
        request_id=new_id(),
        operation_id=operation,
        target_binding_id=target,
        committed_preference_version=2,
    )
    proof = {
        "operation_id": str(operation),
        "committed": True,
        "preference_version": 2,
        "binding_id": str(target),
    }
    assert (await control.finish(commit, proof))["state"] == "committed"
    assert (await control.finish(commit, proof))["state"] == "committed"
    after = await config.get(owner)
    assert after.state == "disabled" and after.binding_id == target and after.generation == 3
    # 切换中原监控开启，关闭意图在 commit 后保持。
    owner = new_id()
    execution, _ = await running(engine, owner)
    command = command.model_copy(update={"owner_user_id": owner, "operation_id": new_id()})
    await control.prepare(command)
    view = await config.get(owner)
    closed = await config.patch(
        owner, MonitorPatch(expected_version=view.version, enabled=False), new_id()
    )
    assert closed.state == "retargeting" and not closed.config.enabled
    commit = commit.model_copy(
        update={"owner_user_id": owner, "operation_id": command.operation_id}
    )
    proof["operation_id"] = str(command.operation_id)
    await control.finish(commit, proof)
    view = await config.get(owner)
    assert view.state == "disabled" and view.next_run_at is None
    await rejected_sample(engine, execution, owner)
    print("并发首次 prepare 幂等、目标冲突、重复 commit 与切换中关闭意图保留：通过")


async def verify_browser(apps, engine, crypto):
    async with browser(apps["gateway"]) as client, browser(apps["gateway"]) as other:
        user = await login(client, await prepare(client, f"synthetic-controls-{new_id()}"))
        assert (await other.get("/api/v1/monitor")).status_code == 401
        view = (await client.get("/api/v1/monitor")).json()["data"]
        assert view["state"] == "disabled" and view["binding_id"] is None
        assert (await client.patch("/api/v1/monitor", json={"enabled": False})).status_code == 428
        assert (
            await client.patch(
                "/api/v1/monitor", json={"expected_version": 1, "interval_minutes": 59}
            )
        ).status_code == 422
        assert (
            await client.patch(
                "/api/v1/monitor", json={"expected_version": 1}, headers={"X-CSRF-Token": "invalid"}
            )
        ).status_code == 403
        responses = await asyncio.gather(
            *(
                client.patch(
                    "/api/v1/monitor",
                    json={
                        "expected_version": view["version"],
                        "interval_minutes": value,
                        "email": "synthetic@example.invalid",
                    },
                )
                for value in [75, 1440]
            )
        )
        assert sorted(r.status_code for r in responses) == [200, 409]
        current = (await client.get("/api/v1/monitor")).json()["data"]
        assert current["config"]["repeat_limit"] == 2
        no_op = await client.patch(
            "/api/v1/monitor", json={"expected_version": current["version"], **current["config"]}
        )
        assert no_op.json()["data"]["generation"] == current["generation"]
        async with engine.connect() as conn:
            row = await first(
                conn,
                "SELECT * FROM monitors WHERE owner_user_id=:owner",
                owner=UUID(user["id"]).bytes,
            )
        assert b"synthetic@example.invalid" not in row["email_ciphertext"]
        assert (
            crypto.open(row["email_ciphertext"], UUID(user["id"]), row["email_version"])
            == "synthetic@example.invalid"
        )
        assert (
            await client.patch(
                "/api/v1/monitor", json={"expected_version": current["version"], "enabled": True}
            )
        ).status_code == 422
    print("Gateway 会话/CSRF、428/422/409、并发版本与无变化保存、邮箱密文和未绑定禁用：通过")


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用显式一次性测试环境")
    apps, _ = await fixture_apps()
    monitoring = apps["monitoring"]
    engine, crypto = monitoring.state.database, monitoring.state.email_crypto
    try:
        await verify_fences(engine, crypto)
        await verify_retarget(engine, crypto)
        await verify_browser(apps, engine, crypto)
        await verify_proof_api(apps)
        await verify_result_race(engine, crypto)
        await verify_credential_update(engine, crypto)
        await verify_compensation(engine, crypto)
        await verify_transaction_rollback(engine, crypto)
        await verify_alert_boundary(engine, crypto)
    finally:
        for app in apps.values():
            if hasattr(app.state, "service_client"):
                await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()
    print("T3 控制基础真实 MySQL 验收通过；未连接真实学校、未启用采集或邮件")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T3 控制验收失败（{type(error).__name__}），检查最后通过步骤") from None
