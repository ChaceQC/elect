"""R1生产2+1池及跨进程GET_LOCK验证；无真实学校身份或外发。"""

import asyncio
import secrets
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest
from login_resource_support import Client, command
from query_resource_support import database, requires_mysql

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.identity import recovery
from services.identity.application.login import LoginSaga
from services.identity.sessions import AppSessions

pytestmark = requires_mysql


def run(case, monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")

    async def scenario():
        async with database("identity", production_pool=True) as engine:
            assert engine.pool.size() == 2 and engine.pool._max_overflow == 1
            sessions = AppSessions(engine, secrets.token_bytes(32))
            client = Client()
            saga = LoginSaga(engine, client, sessions)
            async with asyncio.timeout(15):
                await case(engine, saga, client, sessions)
    asyncio.run(scenario())


def test_three_attempts_finish_or_429_with_session_reads_and_replay(monkeypatch):
    async def case(engine, saga, client, sessions):
        client.release.set()
        token = await saga.login(command(), secrets.token_hex(32), None, new_id())
        client.release.clear()
        client.entered.clear()
        commands = [command() for _ in range(3)]
        nonces = [secrets.token_hex(32) for _ in range(3)]
        admitted = asyncio.create_task(saga.login(commands[0], nonces[0], None, new_id()))
        await client.entered.wait()
        blocked = [asyncio.create_task(saga.login(cmd, nonce, None, new_id()))
                   for cmd, nonce in zip(commands[1:], nonces[1:], strict=True)]
        async with asyncio.timeout(1):
            assert (await sessions.context(token))["user_status"] == "active"
            results = await asyncio.gather(*blocked, return_exceptions=True)
        assert all(isinstance(r, ApiError) and r.status == 429 for r in results)
        assert engine.pool.checkedout() == 1  # 只有外层命名锁连接被保留。
        client.release.set()
        assert await admitted
        for cmd, nonce in zip(commands[1:], nonces[1:], strict=True):
            assert await saga.login(cmd, nonce, None, new_id())
        calls = client.authentications
        assert await saga.login(commands[0], nonces[0], None, new_id())
        assert client.authentications == calls
        async with engine.connect() as conn:
            assert (await first(conn, "SELECT COUNT(*) AS n FROM login_attempts "
                                "WHERE state='session_issued'"))["n"] == 4
        assert not saga.gate.lock.locked() and saga.gate.waiters == 0
    run(case, monkeypatch)


def test_cancel_releases_gate_and_mysql_lock_and_recovery_skips_busy(monkeypatch):
    async def case(engine, saga, client, sessions):
        cmd, nonce = command(), secrets.token_hex(32)
        row = await saga.attempt(cmd, nonce, None)
        identifier = UUID(bytes=row["id"])
        task = asyncio.create_task(saga.login(cmd, nonce, None, new_id()))
        await client.entered.wait()
        async with engine.begin() as conn:
            await execute(conn, "UPDATE login_attempts SET updated_at=DATE_SUB(UTC_TIMESTAMP(6),"
                          "INTERVAL 10 SECOND),next_reconcile_at=UTC_TIMESTAMP(6) WHERE id=:id",
                          id=row["id"])
        app = SimpleNamespace(state=SimpleNamespace(database=engine, login_saga=saga))
        async with asyncio.timeout(1):
            await recovery.recover_tick(app)
        assert (await saga.read(identifier))["state"] == "authenticating"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with engine.connect() as conn:
            free = await first(conn, "SELECT IS_FREE_LOCK(:name) AS free",
                               name=f"identity:login:{identifier}")
            assert free["free"] == 1
        assert not saga.gate.lock.locked() and saga.gate.waiters == 0
        client.release.set()
        await recovery.recover_tick(app)
        assert (await saga.read(identifier))["state"] == "activated"
        assert await saga.login(cmd, nonce, None, new_id())
        assert client.authentications == 1
    run(case, monkeypatch)


def test_same_attempt_is_exclusive_between_processes(monkeypatch):
    async def case(engine, saga, client, sessions):
        identifier = new_id()

        async def child():
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", "import asyncio,json,sys; "
                "sys.path.insert(0,'tests/integration'); "
                "from login_resource_support import child_lock; "
                "asyncio.run(child_lock(*json.load(sys.stdin)))",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            import json

            payload = json.dumps([
                engine.url.render_as_string(hide_password=False), str(identifier),
            ])
            try:
                out, err = await process.communicate(payload.encode())
                assert process.returncode == 0, "隔离子进程失败（不输出连接参数）"
                return out.decode().strip()
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
        async with saga.locked(identifier):
            assert await child() == "busy"
        assert await child() == "acquired"
        assert not saga.gate.lock.locked()
    run(case, monkeypatch)


def test_release_failure_discards_connection(monkeypatch):
    from services.identity.application import login

    real_first = login.first

    async def fail_release(conn, sql, **kwargs):
        if "RELEASE_LOCK" in sql:
            raise RuntimeError("synthetic release failure")
        return await real_first(conn, sql, **kwargs)

    async def case(engine, saga, client, sessions):
        identifier = new_id()
        monkeypatch.setattr(login, "first", fail_release)
        with pytest.raises(RuntimeError, match="synthetic"):
            async with saga.locked(identifier):
                pass
        async with engine.connect() as conn:
            assert (await first(conn, "SELECT IS_FREE_LOCK(:name) AS free",
                                name=f"identity:login:{identifier}"))["free"] == 1
        assert not saga.gate.lock.locked()
    run(case, monkeypatch)


def test_cancel_during_get_lock_discards_unknown_acquisition(monkeypatch):
    from services.identity.application import login

    real_first = login.first

    async def case(engine, saga, client, sessions):
        identifier, acquired = new_id(), asyncio.Event()

        async def uncertain(conn, sql, **kwargs):
            result = await real_first(conn, sql, **kwargs)
            if "GET_LOCK" in sql:
                acquired.set()
                await asyncio.Event().wait()
            return result

        monkeypatch.setattr(login, "first", uncertain)

        async def lock():
            async with saga.locked(identifier):
                pytest.fail("获取结果未返回")

        task = asyncio.create_task(lock())
        await acquired.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with engine.connect() as conn:
            assert (await first(conn, "SELECT IS_FREE_LOCK(:name) AS free",
                                name=f"identity:login:{identifier}"))["free"] == 1
        assert not saga.gate.lock.locked()
    run(case, monkeypatch)
