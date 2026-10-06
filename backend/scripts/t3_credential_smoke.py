"""凭据协调的真实 MySQL/Redis 故障检查；上游为合成学校。"""

import asyncio
import os
from pathlib import Path
from uuid import UUID

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t3_control_fixtures import running
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.identity.revocation import recover_revocation
from services.monitoring.fences import fenced_transaction


async def ready_revoke(identity, operation, *, expect_failure=False):
    async with identity.state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE credential_operations SET next_reconcile_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=UUID(operation).bytes,
        )
    try:
        activity = await recover_revocation(identity)
    except ApiError as error:
        if not expect_failure:
            raise
        assert error.status == 503 and error.code == ErrorCode.DEPENDENCY_UNAVAILABLE
    else:
        assert not expect_failure and activity


async def verify(apps):
    identity, adapter, monitoring = (
        apps[name] for name in ["identity", "school_adapter", "monitoring"]
    )
    async with browser(apps["gateway"]) as client, browser(apps["gateway"]) as other:
        username = f"synthetic-revoke-{new_id()}"
        original_login = await prepare(client, username)
        user = await login(client, original_login)
        owner = UUID(user["id"])
        school = await adapter.state.school_credentials.current(owner)
        execution, _ = await running(monitoring.state.database, owner)
        async with monitoring.state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE monitors SET credential_ref=:ref WHERE id=:id",
                ref=school["id"],
                id=execution.monitor_id.bytes,
            )
        original_call = identity.state.service_client.call
        assert (
            await client.request("DELETE", "/api/v1/auth/school-credential", json={})
        ).status_code == 428
        assert (
            await client.request(
                "DELETE",
                "/api/v1/auth/school-credential",
                json={"expected_version": 1},
                headers={"X-CSRF-Token": "wrong"},
            )
        ).status_code == 403
        assert (
            await client.request(
                "DELETE", "/api/v1/auth/school-credential", json={"expected_version": 2}
            )
        ).status_code == 409
        # 原登录已验证暂存，但 Identity 尚未持久建档，随后发生撤回。
        stale_login = await prepare(client, username)

        async def lose_auth(receiver, path, *args, **kwargs):
            result = await original_call(receiver, path, *args, **kwargs)
            if path == "/login-attempts/authenticate":
                raise ApiError(
                    503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic lost response", True
                )
            return result

        identity.state.service_client.call = lose_auth
        assert (await client.post("/api/v1/auth/login", json=stale_login)).status_code == 503
        identity.state.service_client.call = original_call
        response = await client.request(
            "DELETE", "/api/v1/auth/school-credential", json={"expected_version": 1}
        )
        assert response.status_code == 202
        operation = response.json()["data"]["operation_id"]
        assert (await other.get(f"/api/v1/operations/{operation}")).status_code == 401
        await login(other, await prepare(other, f"synthetic-revoke-other-{new_id()}"))
        assert (await other.get(f"/api/v1/operations/{operation}")).status_code == 404
        me = (await client.get("/api/v1/auth/me")).json()["data"]
        assert me["credential_status"] == "revoking" and not me["consent"]["credential_use_allowed"]
        assert me["credential_revoke_operation"]["id"] == operation

        async def block_barrier(receiver, path, *args, **kwargs):
            if path == "/credentials/prepare-revoke":
                raise ApiError(
                    503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic barrier down", True
                )
            return await original_call(receiver, path, *args, **kwargs)

        identity.state.service_client.call = block_barrier
        await ready_revoke(identity, operation, expect_failure=True)
        row = await adapter.state.school_credentials.current(owner)
        assert row["status"] == "active" and row["ciphertext"]

        async def lose_revoke(receiver, path, *args, **kwargs):
            value = await original_call(receiver, path, *args, **kwargs)
            if path == "/credentials/revoke":
                raise ApiError(
                    503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic lost response", True
                )
            return value

        identity.state.service_client.call = lose_revoke
        await ready_revoke(identity, operation, expect_failure=True)
        row = await adapter.state.school_credentials.current(owner)
        assert row["status"] == "revoked" and not row["ciphertext"] and not row["wrapped_dek"]
        assert not row["school_user_id_ciphertext"] and not row["use_allowed"]
        async with adapter.state.database.connect() as conn:
            remnants = await first(
                conn,
                "SELECT COUNT(*) AS n FROM credential_staging WHERE credential_ref=:ref "
                "AND (LENGTH(encrypted_payload)>0 OR LENGTH(wrapped_dek)>0)",
                ref=school["id"],
            )
        assert remnants["n"] == 0
        view = (await client.get("/api/v1/monitor")).json()["data"]
        assert not view["config"]["enabled"] and view["cancel_pending"]
        try:
            async with fenced_transaction(monitoring.state.database, execution):
                raise AssertionError("撤回后的旧运行仍可提交")
        except ApiError as error:
            assert error.status == 409
        identity.state.service_client.call = original_call
        await ready_revoke(identity, operation)
        state = (await client.get(f"/api/v1/operations/{operation}")).json()["data"]
        assert state["state"] == "succeeded"
        me = (await client.get("/api/v1/auth/me")).json()["data"]
        assert me["credential_status"] == "revoked" and me["student_id"] == username
        assert me["credential_revoke_operation"] is None
        key = f"school_adapter:token:{UUID(bytes=school['id'])}:1"
        assert await adapter.state.school_store.get_secret(key) is None
        # 被撤回作废的旧验证暂存不得重新激活，原 session_issued 也不能重放发会话。
        assert (await client.post("/api/v1/auth/login", json=stale_login)).status_code == 400
        token = client.cookies.get("__Host-elect_session")
        client.cookies.delete("__Host-elect_session")
        repeated = await client.post("/api/v1/auth/login", json=original_login)
        assert repeated.status_code == 409 and "__Host-elect_session" not in repeated.headers.get(
            "set-cookie", ""
        )
        client.cookies.set("__Host-elect_session", token, domain="elect.test.local", path="/")
        fresh = await login(client, await prepare(client, username))
        assert fresh["credential_version"] == 2 and fresh["consent"]["credential_use_allowed"]
        assert not (await client.get("/api/v1/monitor")).json()["data"]["config"]["enabled"]
        replay = await client.request(
            "DELETE", "/api/v1/auth/school-credential", json={"expected_version": 1}
        )
        assert replay.json()["data"]["operation_id"] == operation
        row = await adapter.state.school_credentials.current(owner)
        assert row["status"] == "active" and row["version"] == 2
        async with adapter.state.database.connect() as conn:
            count = await first(
                conn,
                "SELECT COUNT(*) AS n FROM credential_revocations WHERE owner_user_id=:owner",
                owner=owner.bytes,
            )
        assert count["n"] == 1
        print(
            "持久撤回/操作恢复、先屏障后删除、响应丢失、应用会话保留、旧登录/旧撤回重放隔离：通过"
        )


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用一次性测试环境")
    apps, _ = await fixture_apps()
    try:
        await verify(apps)
        from scripts.t3_credential_faults import verify_faults

        await verify_faults(apps, ready_revoke)
        from scripts.t3_permit_smoke import verify_permits

        await verify_permits(
            apps["monitoring"].state.database, apps["monitoring"].state.email_crypto
        )
        async with apps["identity"].state.database.connect() as conn:
            pending = await first(
                conn,
                "SELECT COUNT(*) AS n FROM users WHERE credential_operation_id IS NOT NULL",
            )
            assert pending["n"] == 0
        async with apps["room"].state.database.connect() as conn:
            pending = await first(
                conn,
                "SELECT COUNT(*) AS n FROM room_operations WHERE type='binding_sync' "
                "AND state IN ('accepted','running')",
            )
            assert pending["n"] == 0
        print("合成凭据操作槽和学校同步任务均已终结，可安全恢复真实 Worker：通过")
    finally:
        for app in apps.values():
            if hasattr(app.state, "service_client"):
                await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T3 凭据检查失败（{type(error).__name__}）") from None
