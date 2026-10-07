"""合成学校 + 实际数据库：激活阶段故障、补偿、每用户串行和迟到缓存。"""

import asyncio
from types import SimpleNamespace
from uuid import UUID

from scripts.t2_smoke import browser, login, prepare
from scripts.t3_control_fixtures import running
from services.common.database import create_database
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.identity.application.login import LoginSaga
from services.monitoring.fences import fenced_transaction


async def activation_fault(apps, path, *, expired=False):
    identity, adapter, monitoring = (
        apps[key] for key in ["identity", "school_adapter", "monitoring"]
    )
    async with browser(apps["gateway"]) as client:
        name = f"synthetic-activation-{new_id()}"
        user = await login(client, await prepare(client, name))
        owner = UUID(user["id"])
        credential = await adapter.state.school_credentials.current(owner)
        execution, _ = await running(monitoring.state.database, owner)
        async with monitoring.state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE monitors SET credential_ref=:ref WHERE owner_user_id=:owner",
                ref=credential["id"],
                owner=owner.bytes,
            )
        body = await prepare(client, name)
        original = identity.state.service_client.call

        async def interrupted(receiver, called_path, *args, **kwargs):
            if expired and called_path == path:
                async with adapter.state.database.begin() as conn:
                    await execute(
                        conn,
                        "UPDATE credential_staging SET expires_at=DATE_SUB(UTC_TIMESTAMP(6),"
                        "INTERVAL 1 SECOND) WHERE credential_ref=:ref AND state='staged'",
                        ref=credential["id"],
                    )
            value = await original(receiver, called_path, *args, **kwargs)
            if called_path == path:
                raise ApiError(
                    503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic lost response", True
                )
            return value

        identity.state.service_client.call = interrupted
        try:
            response = await client.post("/api/v1/auth/login", json=body)
        finally:
            identity.state.service_client.call = original
        assert response.status_code == (400 if expired else 503)
        async with identity.state.database.connect() as conn:
            row = await first(
                conn,
                "SELECT * FROM login_attempts WHERE user_id=:owner "
                "ORDER BY created_at DESC LIMIT 1",
                owner=owner.bytes,
            )
            account = await first(conn, "SELECT * FROM users WHERE id=:owner", owner=owner.bytes)
        if expired:
            assert row["state"] == "failed" and account["credential_operation_id"] is None
            assert account["credential_version"] == 1
            view = (await client.get("/api/v1/monitor")).json()["data"]
            assert view["state"] == "active" and view["generation"] > execution.generation
        else:
            assert row["state"] == "activating" and account["credential_operation_id"] == row["id"]
            blocked = await client.request(
                "DELETE", "/api/v1/auth/school-credential", json={"expected_version": 1}
            )
            assert blocked.status_code == 409
            # 崩溃后的协调使用持久记录；不需要原浏览器密码或重新执行学校 A03。
            async with identity.state.login_saga.locked(UUID(bytes=row["id"])):
                await identity.state.login_saga.advance(row, new_id())
            current = await login(client, body)
            assert current["credential_version"] == 2
        try:
            async with fenced_transaction(monitoring.state.database, execution):
                raise AssertionError("凭据改代/补偿后旧运行越过栅栏")
        except ApiError as error:
            assert error.status == 409
    print(
        f"激活故障 {path}、并发撤回拒绝/恢复"
        if not expired
        else "暂存过期补偿、用户槽释放、旧执行仍失效",
        "：通过",
    )


async def late_token(apps, ready_revoke):
    adapter = apps["school_adapter"].state
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, f"synthetic-late-token-{new_id()}"))
        owner = UUID(user["id"])
        row = await adapter.school_credentials.current(owner)
        key = f"school_adapter:token:{UUID(bytes=row['id'])}:1"
        await adapter.school_store.call("delete", key)
        reached, resume = asyncio.Event(), asyncio.Event()
        original = adapter.school_store.put_secret

        async def delayed(cache_key, value, **kwargs):
            if cache_key == key:
                reached.set()
                await resume.wait()
            await original(cache_key, value, **kwargs)

        adapter.school_store.put_secret = delayed
        task = asyncio.create_task(
            adapter.school_sessions.read(
                owner, new_id(), "/api/base/roomUser/selectRoomListByUserId", {}, include_user=True
            )
        )
        try:
            await asyncio.wait_for(reached.wait(), 10)
            response = await client.request(
                "DELETE", "/api/v1/auth/school-credential", json={"expected_version": 1}
            )
            assert response.status_code == 202
            await ready_revoke(apps["identity"], response.json()["data"]["operation_id"])
            resume.set()
            try:
                await task
                raise AssertionError("撤回后迟到 token 仍可返回学校结果")
            except ApiError as error:
                assert error.code == ErrorCode.SCHOOL_REAUTH_REQUIRED
            assert await adapter.school_store.get_secret(key) is None
        finally:
            resume.set()
            adapter.school_store.put_secret = original
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    print("真实 Redis 写入与撤回交错：迟到 token 清除、学校结果拒绝：通过")


async def verify_faults(apps, ready_revoke):
    for path in [
        "/credentials/prepare-update",
        "/credentials/activate",
        "/credentials/commit-update",
    ]:
        await activation_fault(apps, path)
    await activation_fault(apps, "/credentials/activate", expired=True)
    await late_token(apps, ready_revoke)
    await late_authentication(apps, ready_revoke)


async def late_authentication(apps, ready_revoke):
    adapter = apps["school_adapter"].state
    identity = apps["identity"].state
    # R1本上下文正在登录时，恢复门必须跳过；独立恢复上下文模拟standalone进程边界。
    engine = create_database(identity.runtime.db_url.get_secret_value())
    recovery = SimpleNamespace(state=SimpleNamespace(
        database=engine, service_client=identity.service_client,
        login_saga=LoginSaga(engine, identity.service_client, identity.login_saga.sessions)))
    async with browser(apps["gateway"]) as client:
        name = f"synthetic-late-auth-{new_id()}"
        user = await login(client, await prepare(client, name))
        owner = UUID(user["id"])
        body = await prepare(client, name)
        reached, resume = asyncio.Event(), asyncio.Event()
        original = adapter.school_protocol.authenticate

        async def delayed(*args, **kwargs):
            value = await original(*args, **kwargs)
            reached.set()
            await resume.wait()
            return value

        adapter.school_protocol.authenticate = delayed
        task = asyncio.create_task(client.post("/api/v1/auth/login", json=body))
        try:
            await asyncio.wait_for(reached.wait(), 10)
            response = await client.request(
                "DELETE", "/api/v1/auth/school-credential", json={"expected_version": 1}
            )
            assert response.status_code == 202
            operation = response.json()["data"]["operation_id"]
            try:
                await ready_revoke(apps["identity"], operation)
            except ApiError as error:
                assert error.status == 429
            else:
                raise AssertionError("同上下文恢复没有遵守登录执行门")
            await ready_revoke(recovery, operation)
            resume.set()
            rejected = await task
            assert rejected.status_code == 409
            assert "__Host-elect_session" not in rejected.headers.get("set-cookie", "")
            row = await adapter.school_credentials.current(owner)
            assert row["status"] == "revoked" and not row["ciphertext"]
        finally:
            resume.set()
            adapter.school_protocol.authenticate = original
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await engine.dispose()
    print("人工学校认证在撤回前开始、撤回后响应：旧认证不得暂存/激活：通过")
