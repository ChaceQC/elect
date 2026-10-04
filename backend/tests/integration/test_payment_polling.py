"""显式启用的一次性MySQL验证；只迁移Payment，学校/Room调用全部合成。"""

import asyncio
import os
import secrets
import subprocess
import time
from types import SimpleNamespace

import pytest
from alembic import command
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.migrations import configuration
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first
from services.payment import api, cancellation, jobs, qr, reconciliation

pytestmark = pytest.mark.skipif(
    os.environ.get("ELECT_TEST_PAYMENT_DISPOSABLE") != "1",
    reason="需要明确允许启动一次性Payment MySQL容器",
)


@pytest.fixture(scope="module")
def database_url():
    name = f"elect-test-polling-{secrets.token_hex(5)}"
    password = secrets.token_hex(24)
    env = {**os.environ, "MYSQL_ROOT_PASSWORD": password}

    def docker(*args):
        return subprocess.run(["docker", *args], env=env, capture_output=True,
                              text=True, encoding="utf-8", check=True).stdout.strip()

    try:
        docker("run", "-d", "--name", name, "--tmpfs", "/var/lib/mysql",
               "-p", "127.0.0.1::3306", "-e", "MYSQL_ROOT_PASSWORD",
               "-e", "MYSQL_ROOT_HOST=%", "-e", "MYSQL_DATABASE=elect_payment", "mysql:8.4.6")
        port = int(docker("port", name, "3306/tcp").rsplit(":", 1)[1])
        url = URL.create("mysql+asyncmy", username="root", password=password,
                         host="127.0.0.1", port=port, database="elect_payment")

        async def migrate():
            engine = create_async_engine(url, hide_parameters=True)
            try:
                async with engine.begin() as conn:
                    assert (await execute(conn, "SELECT VERSION()")).scalar().startswith("8.4.")

                    def upgrade(connection):
                        config = configuration("payment")
                        config.attributes["connection"] = connection
                        command.upgrade(config, "head")

                    await conn.run_sync(upgrade)
            finally:
                await engine.dispose()

        for attempt in range(60):
            try:
                asyncio.run(migrate())
                break
            except Exception:
                if attempt == 59:
                    raise RuntimeError("一次性Payment数据库未就绪") from None
                time.sleep(1)
        yield url
    finally:
        docker("rm", "-f", "-v", name)


async def seed(engine):
    order, owner, operation = new_id(), new_id(), new_id()
    async with engine.begin() as conn:
        await execute(conn, "INSERT INTO payment_owners VALUES (:owner)", owner=owner.bytes)
        await execute(
            conn,
            "INSERT INTO payment_orders (id,owner_user_id,binding_id,binding_display_name,"
            "credential_ref,credential_version,amount,currency,idempotency_key_hash,"
            "request_digest,state,version,upstream_operation_id,next_check_at) "
            "VALUES (:id,:owner,:binding,'合成寝室',:credential,1,1.00,'CNY',:hash,"
            ":hash,'awaiting_payment',1,:upstream,UTC_TIMESTAMP(6))",
            id=order.bytes, owner=owner.bytes, binding=new_id().bytes, credential=new_id().bytes,
            hash=secrets.token_bytes(32), upstream=new_id().bytes,
        )
        await execute(
            conn,
            "INSERT INTO payment_operations (id,owner_user_id,order_id,kind,request_digest,"
            "state,execution_epoch,next_attempt_at) "
            "VALUES (:id,:owner,:order,'create_order',:hash,'accepted',1,UTC_TIMESTAMP(6))",
            id=operation.bytes, owner=owner.bytes, order=order.bytes, hash=secrets.token_bytes(32),
        )
    return order, owner


async def read(engine, order):
    async with engine.connect() as conn:
        return await first(conn, "SELECT * FROM payment_orders WHERE id=:id", id=order.bytes)


def test_slow_check_is_unique_and_qr_does_not_postpone_two_second_schedule(database_url):
    async def verify():
        engine = create_async_engine(database_url, hide_parameters=True)
        try:
            order, _ = await seed(engine)
            entered, release = asyncio.Event(), asyncio.Event()
            calls = []

            async def call(*args, **kwargs):
                calls.append(args[1])
                entered.set()
                await release.wait()
                return {"order_state": "status_unknown", "error_code": None}

            app = SimpleNamespace(state=SimpleNamespace(
                database=engine, service_client=SimpleNamespace(call=call),
            ))
            worker = await jobs.claim(engine, order)
            async with asyncio.timeout(5):
                task = asyncio.create_task(reconciliation.check_tick(app, order_id=order))
                await entered.wait()
                assert not await reconciliation.check_tick(app, order_id=order)
                due = (await read(engine, order))["next_check_at"]
                assert await jobs.update(
                    engine, worker, qr_status="ready", operation_state="succeeded",
                )
                assert (await read(engine, order))["next_check_at"] == due
                release.set()
                assert await task
            row = await read(engine, order)
            assert row["state"] == "status_unknown" and row["qr_status"] == "ready"
            assert (row["next_check_at"] - row["last_checked_at"]).total_seconds() == 2
            assert calls == ["/payments/check"]
            assert not await reconciliation.check_tick(app, order_id=order)
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_confirmed_payment_blocks_late_qr_and_continues_balance_refresh(database_url):
    async def verify():
        engine = create_async_engine(database_url, hide_parameters=True)
        try:
            order, owner = await seed(engine)
            balance_id = new_id()
            balance_done, checks = False, []

            async def call(service, path, *args, **kwargs):
                checks.append(path)
                if path == "/payments/check":
                    return {"order_state": "paid_confirmed"}
                if path == "/browser/balance-refresh":
                    return {"operation_id": str(balance_id)}
                return {"state": "succeeded" if balance_done else "running"}

            app = SimpleNamespace(state=SimpleNamespace(
                database=engine, service_client=SimpleNamespace(call=call),
            ))
            worker = await jobs.claim(engine, order)
            async with asyncio.timeout(5):
                checked, refreshed = await asyncio.gather(
                    reconciliation.check_tick(app, order_id=order),
                    qr.refresh(engine, owner, order, "synthetic-parallel-qr-refresh"),
                    return_exceptions=True,
                )
            assert checked is True
            if isinstance(refreshed, Exception):
                assert isinstance(refreshed, ApiError) and refreshed.status == 409
            assert not await jobs.update(engine, worker, order_state="status_unknown")
            row = await read(engine, order)
            assert row["state"] == "paid_confirmed" and row["balance_refresh_state"] == "pending"
            balance_done = True
            async with engine.begin() as conn:
                await execute(conn, "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) "
                              "WHERE id=:id", id=order.bytes)
            assert await reconciliation.check_tick(app, order_id=order)
            assert (await read(engine, order))["balance_refresh_state"] == "succeeded"
            assert not await reconciliation.claim(engine, order)
            assert checks.count("/payments/check") == checks.count("/browser/balance-refresh") == 1
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_cancel_during_check_and_browser_reads_cannot_restart_order(database_url):
    async def verify():
        engine = create_async_engine(database_url, hide_parameters=True)
        try:
            order, owner = await seed(engine)
            entered, release = asyncio.Event(), asyncio.Event()

            async def call(*args, **kwargs):
                entered.set()
                await release.wait()
                return {"order_state": "status_unknown"}

            app = SimpleNamespace(state=SimpleNamespace(
                database=engine, service_client=SimpleNamespace(call=call),
            ))
            principal = Principal("payment", owner, 1, new_id())
            async with asyncio.timeout(5):
                task = asyncio.create_task(reconciliation.check_tick(app, order_id=order))
                await entered.wait()
                await cancellation.cancel(engine, principal, order, 1)
                release.set()
                assert await task
            request = SimpleNamespace(app=app)
            for _ in range(3):
                await api.read_order(SimpleNamespace(order_id=order), request, principal)
            row = await read(engine, order)
            assert row["cancelled_at"] and row["next_check_at"] is None
            assert not await reconciliation.claim(engine, order)
            assert not await jobs.claim(engine, order)
        finally:
            await engine.dispose()

    asyncio.run(verify())
