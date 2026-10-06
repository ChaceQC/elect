"""显式 opt-in 的隔离查询数据库；只迁移随机新建库，不读取业务配置。"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.migrations import configuration
from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.repository import lock_monitor

ROOT_FILE = os.environ.get("ELECT_TEST_MYSQL_ROOT_URL_FILE")
LOCAL_HOST = os.environ.get("ELECT_TEST_QUERY_MYSQL_HOST")
ENABLED = (ROOT_FILE and os.environ.get("ELECT_TEST_MYSQL_DISPOSABLE") == "1"
           or LOCAL_HOST == "query-mysql")
requires_mysql = pytest.mark.skipif(not ENABLED, reason="需要显式一次性 MySQL 8.4 环境")


def root_url():
    if ROOT_FILE:
        return make_url(Path(ROOT_FILE).read_text(encoding="utf-8").strip())
    return make_url("mysql+asyncmy://root@query-mysql/mysql")


def migrate(connection, domain, revision="head"):
    config = configuration(domain)
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


@asynccontextmanager
async def database(domain, *, production_pool=False):
    url = root_url()
    name = "elect_query_test_" + uuid4().hex
    root = create_async_engine(url, hide_parameters=True)
    from services.common.database import create_database

    engine = create_database(url.set(database=name)) if production_pool else create_async_engine(
        url.set(database=name), hide_parameters=True, isolation_level="READ COMMITTED",
        pool_size=8, max_overflow=0,
    )
    try:
        async with root.begin() as conn:
            assert (await first(conn, "SELECT VERSION() AS v"))["v"].startswith("8.4.")
            await execute(conn, f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
        async with engine.begin() as conn:
            await conn.run_sync(migrate, domain)
            await conn.run_sync(migrate, domain)  # 升级入口可重复运行。
        yield engine
    finally:
        await engine.dispose()
        async with root.begin() as conn:
            await execute(conn, f"DROP DATABASE IF EXISTS `{name}`")
        await root.dispose()


def run(domain, case):
    async def scenario():
        async with database(domain) as engine:
            await case(engine)
    asyncio.run(scenario())


async def seed_samples(engine, owner, binding, count=3):
    async with engine.begin() as conn:
        monitor = await lock_monitor(conn, owner)
        for index in range(count):
            run_id, sample_id = new_id().bytes, new_id().bytes
            await execute(
                conn, "INSERT INTO monitor_runs (id,monitor_id,generation,scheduled_for,"
                "binding_id,credential_version,state,version,attempt_count,execution_epoch) "
                "VALUES (:id,:monitor,1,:time,:binding,1,'succeeded',1,0,1)",
                id=run_id, monitor=monitor["id"], binding=binding.bytes,
                time=datetime(2026, 9, 1, 0, index),
            )
            await execute(
                conn, "INSERT INTO monitor_samples (id,run_id,monitor_id,owner_user_id,"
                "binding_id,captured_at,balance,quality,credential_version) "
                "VALUES (:id,:run,:monitor,:owner,:binding,:time,25.50,'balance_only',1)",
                id=sample_id, run=run_id, monitor=monitor["id"], owner=owner.bytes,
                binding=binding.bytes, time=datetime(2026, 9, 1, 0, index),
            )


async def seed_binding(engine, owner, binding):
    async with engine.begin() as conn:
        room_id = new_id().bytes
        await execute(
            conn, "INSERT INTO rooms (id,school_id,school_room_id,building_name,room_no,"
            "metadata_version) VALUES (:id,'synthetic',:school,'test','101',1)",
            id=room_id, school=str(new_id()),
        )
        await execute(
            conn, "INSERT INTO room_bindings (id,owner_user_id,room_id,status) "
            "VALUES (:id,:owner,:room,'active')",
            id=binding.bytes, owner=owner.bytes, room=room_id,
        )


async def counts(engine, tables):
    async with engine.begin() as conn:
        return [(await first(conn, f"SELECT COUNT(*) AS n FROM {table}"))["n"]
                for table in tables]
