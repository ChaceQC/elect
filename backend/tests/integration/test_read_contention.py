"""R5.1真实MySQL：权威会话检查、续期竞态及无锁一致性读。"""

import asyncio
import hashlib
import secrets
from datetime import timedelta
from time import perf_counter
from unittest.mock import AsyncMock

import pytest
from query_resource_support import database, requires_mysql
from sqlalchemy import event

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute
from services.identity.sessions import AppSessions
from services.monitoring.queries import MonitorQueries
from services.monitoring.repository import lock_monitor

pytestmark = requires_mysql


def run(domain, case, monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")

    async def scenario():
        async with database(domain, production_pool=True) as engine:
            async with asyncio.timeout(15):
                await case(engine)
    asyncio.run(scenario())


async def session_fixture(engine):
    sessions = AppSessions(engine, secrets.token_bytes(32))
    owner, sid, token = new_id(), new_id(), secrets.token_urlsafe(32)
    async with engine.begin() as conn:
        await execute(conn, "INSERT INTO users "
                      "(id,school_id,credential_ref,status,session_version) "
                      "VALUES (:id,'synthetic',:ref,'active',1)",
                      id=owner.bytes, ref=new_id().bytes)
        await execute(conn, "INSERT INTO app_sessions (id,user_id,token_hash,csrf_hash,expires_at,"
                      "absolute_expires_at,last_seen_at,session_version) VALUES "
                      "(:id,:owner,:hash,:csrf,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 12 HOUR),"
                      "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 7 DAY),"
                      "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 61 SECOND),1)",
                      id=sid.bytes, owner=owner.bytes, hash=sessions.digest(token),
                      csrf=hashlib.sha256(sessions.csrf(token).encode()).digest())
    return sessions, token, owner, sid


def test_session_updates_are_coalesced_and_expiry_stays_authoritative(monkeypatch):
    async def case(engine):
        sessions, token, _, sid = await session_fixture(engine)
        writes = []

        def count(conn, cursor, sql, params, context, many):
            if sql.startswith("UPDATE app_sessions"):
                writes.append(cursor.rowcount)
        event.listen(engine.sync_engine, "after_cursor_execute", count)
        start = perf_counter()
        for _ in range(40):
            row = await sessions.context(token)
        elapsed = perf_counter() - start
        assert writes == [1]
        assert row["expires_at"].replace(tzinfo=None) - row["last_seen_at"] == timedelta(hours=12)
        start = perf_counter()
        for _ in range(40):
            async with engine.begin() as conn:
                await execute(conn, "SELECT s.*,u.status FROM app_sessions s JOIN users u "
                              "ON s.user_id=u.id WHERE s.id=:id FOR UPDATE", id=sid.bytes)
                await execute(conn, "UPDATE app_sessions SET last_seen_at=UTC_TIMESTAMP(6),"
                              "expires_at=LEAST(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 12 HOUR),"
                              "absolute_expires_at),updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                              id=sid.bytes)
        baseline_elapsed = perf_counter() - start
        assert len(writes) == 41
        writes[:] = [1]
        # 到期前最后一秒仍可续期；绝对上限不能延长。
        async with engine.begin() as conn:
            await execute(conn, "UPDATE app_sessions SET last_seen_at="
                          "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 61 SECOND),expires_at="
                          "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 1 SECOND),absolute_expires_at="
                          "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND) WHERE id=:id",
                          id=sid.bytes)
        rows = await asyncio.gather(*(sessions.context(token) for _ in range(6)))
        assert all(r["expires_at"].replace(tzinfo=None) == r["absolute_expires_at"] for r in rows)
        assert sum(writes) == 3  # 正常续期一次、夹具更新一次、并发续期仅一次。
        async with engine.begin() as conn:
            await execute(conn, "UPDATE app_sessions SET expires_at=UTC_TIMESTAMP(6) "
                          "WHERE id=:id", id=sid.bytes)
        assert await sessions.context(token, required=False) is None
        print(f"R5 session: requests=40 renewed_rows=40->1 "
              f"seconds={baseline_elapsed:.4f}->{elapsed:.4f}")
    run("identity", case, monkeypatch)


@pytest.mark.parametrize("change", ["logout", "disable", "version", "sliding", "absolute"])
def test_renewal_cannot_revive_concurrently_invalidated_session(monkeypatch, change):
    async def case(engine):
        sessions, token, owner, sid = await session_fixture(engine)
        entered, release = asyncio.Event(), asyncio.Event()
        original = sessions.read

        async def paused(conn, value):
            row = await original(conn, value)
            if not entered.is_set():
                entered.set()
                await release.wait()
            return row
        sessions.read = paused
        reader = asyncio.create_task(sessions.context(token, required=False))
        await entered.wait()
        async with engine.begin() as conn:
            if change in {"disable", "version"}:
                clause = "status='disabled'" if change == "disable" else "session_version=2"
                await execute(conn, f"UPDATE users SET {clause} WHERE id=:id", id=owner.bytes)
            else:
                field = {"logout": "revoked_at", "sliding": "expires_at",
                         "absolute": "absolute_expires_at"}[change]
                await execute(conn, f"UPDATE app_sessions SET {field}=UTC_TIMESTAMP(6) "
                              "WHERE id=:id", id=sid.bytes)
        release.set()
        assert await reader is None
        with pytest.raises(ApiError) as failure:
            await sessions.context(token)
        assert failure.value.status == 401
    run("identity", case, monkeypatch)


def test_monitor_initialization_and_read_snapshot_do_not_block_controls(monkeypatch):
    async def case(engine):
        owner = new_id()
        crypto = AsyncMock()
        crypto.open = lambda *args: None
        queries = MonitorQueries(engine, crypto)
        values = await asyncio.gather(*(queries.get(owner) for _ in range(6)))
        assert len({v.id for v in values}) == 1
        writes, locks = [], []

        def observe(conn, cursor, sql, params, context, many):
            if sql.startswith(("INSERT", "UPDATE")):
                writes.append(sql.split()[0])
            if "FOR UPDATE" in sql:
                locks.append(1)
        event.listen(engine.sync_engine, "after_cursor_execute", observe)
        for _ in range(10):
            await queries.get(owner)
        assert not writes and not locks
        # 同条件旧路径：每次lock_monitor产生写锁，暂停读时控制事务必须等待。
        for _ in range(10):
            async with engine.begin() as conn:
                await queries.view(conn, await lock_monitor(conn, owner))
        assert len(writes) == 10 and len(locks) == 10
        async with engine.begin() as conn:
            await lock_monitor(conn, owner)
            waiting = asyncio.Event()

            async def control():
                waiting.set()
                async with engine.begin() as other:
                    await lock_monitor(other, owner)
            baseline_writer = asyncio.create_task(control())
            await waiting.wait()
            await asyncio.sleep(0.05)
            assert not baseline_writer.done()
        await baseline_writer
        entered, release = asyncio.Event(), asyncio.Event()
        original = queries.view

        async def paused(conn, row):
            entered.set()
            await release.wait()
            return await original(conn, row)
        queries.view = paused
        reader = asyncio.create_task(queries.get(owner))
        await entered.wait()
        start = perf_counter()
        async with engine.begin() as conn:
            row = await lock_monitor(conn, owner)
            await execute(conn, "UPDATE monitors SET interval_minutes=120,version=version+1 "
                          "WHERE id=:id", id=row["id"])
            await execute(conn, "INSERT INTO monitor_runs (id,monitor_id,generation,scheduled_for,"
                          "binding_id,credential_version,state,version,attempt_count,"
                          "execution_epoch) "
                          "VALUES (:id,:monitor,1,UTC_TIMESTAMP(6),:binding,1,'pending',1,0,1)",
                          id=new_id().bytes, monitor=row["id"], binding=new_id().bytes)
        control_seconds = perf_counter() - start
        release.set()
        old = await reader
        assert old.config.interval_minutes == 60 and old.last_run is None
        fresh = await queries.get(owner)
        assert fresh.config.interval_minutes == 120 and fresh.last_run.state == "pending"
        async with engine.connect() as conn:
            assert await conn.get_isolation_level() == "READ COMMITTED"
        print(f"R5 monitor: reads=10 writes=10->0 exclusive_locks=10->0 "
              f"blocked_control=>0.05s->none control_seconds={control_seconds:.4f}")
    run("monitoring", case, monkeypatch)
