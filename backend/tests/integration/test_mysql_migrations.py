"""显式 opt-in 的临时 MySQL 8.4 验证；不连接学校。"""

import asyncio
import os
import secrets
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from services.common.ids import new_id
from services.common.migration_runtime import DATABASES

ROOT_SECRET = os.environ.get("ELECT_TEST_MYSQL_ROOT_URL_FILE")
pytestmark = pytest.mark.skipif(
    not ROOT_SECRET or os.environ.get("ELECT_TEST_MYSQL_DISPOSABLE") != "1",
    reason="需要显式配置一次性 MySQL 8.4 测试库",
)


async def prepare_accounts(root_url, tmp_path):
    engine = create_async_engine(root_url, hide_parameters=True)
    credentials = {}
    try:
        async with engine.begin() as connection:
            assert (await connection.execute(text("SELECT VERSION()"))).scalar().startswith("8.4.")
            for domain, database in DATABASES.items():
                await connection.execute(
                    text(
                        f"CREATE DATABASE IF NOT EXISTS {database} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                    )
                )
                credentials[domain] = {}
                short = database.removeprefix("elect_")
                for role, privileges in [
                    (
                        "ddl",
                        "CREATE, ALTER, DROP, INDEX, REFERENCES, SELECT, INSERT, UPDATE, DELETE",
                    ),
                    ("app", "SELECT, INSERT, UPDATE, DELETE"),
                ]:
                    user = f"elect_{short}_{role}"
                    password = secrets.token_hex(24)
                    await connection.execute(text(f"DROP USER IF EXISTS '{user}'@'%'"))
                    await connection.execute(
                        text(f"CREATE USER '{user}'@'%' IDENTIFIED BY :password"),
                        {"password": password},
                    )
                    await connection.execute(
                        text(f"GRANT {privileges} ON {database}.* TO '{user}'@'%'")
                    )
                    url = root_url.set(username=user, password=password, database=database)
                    credentials[domain][role] = url
                    path = tmp_path / f"{domain}_{role}_url"
                    path.write_text(url.render_as_string(hide_password=False))
                    path.chmod(0o600)
        return credentials
    finally:
        await engine.dispose()


async def verify_empty_isolated_databases(root_url, credentials):
    root_engine = create_async_engine(root_url, hide_parameters=True)
    try:
        async with root_engine.connect() as root_connection:
            foreign = await root_connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE "
                    "WHERE TABLE_SCHEMA LIKE 'elect_%' AND REFERENCED_TABLE_SCHEMA IS NOT NULL "
                    "AND TABLE_SCHEMA <> REFERENCED_TABLE_SCHEMA"
                )
            )
            assert foreign.scalar() == 0
        for domain, roles in credentials.items():
            engine = create_async_engine(roles["app"], hide_parameters=True)
            try:
                async with engine.connect() as connection:
                    tables = [row[0] for row in await connection.execute(text("SHOW TABLES"))]
                    assert "alembic_version" in tables and "outbox_events" in tables
                    for name in tables:
                        if name != "alembic_version":
                            assert (
                                await connection.execute(text(f"SELECT COUNT(*) FROM `{name}`"))
                            ).scalar() == 0
                    other = "elect_room" if domain != "room" else "elect_identity"
                    with pytest.raises(DBAPIError):
                        await connection.execute(text(f"SELECT * FROM {other}.alembic_version"))
                    with pytest.raises(DBAPIError):
                        await connection.execute(text("CREATE TABLE forbidden_ddl (id INT)"))
            finally:
                await engine.dispose()
    finally:
        await root_engine.dispose()


async def verify_monitor_constraints(url):
    engine = create_async_engine(url, hide_parameters=True)
    values = {"id": new_id().bytes, "owner": new_id().bytes, "binding": new_id().bytes}
    monitor_sql = text(
        "INSERT INTO monitors (id,owner_user_id,desired_enabled,state,health,interval_minutes,"
        "repeat_limit,threshold,email_version,version,generation,consecutive_failures) "
        "VALUES (:id,:owner,0,'disabled','unavailable',:interval,2,20.00,1,1,1,0)"
    )
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                with pytest.raises(DBAPIError):
                    await connection.execute(monitor_sql, {**values, "interval": 59})
                await connection.execute(monitor_sql, {**values, "interval": 60})
                with pytest.raises(DBAPIError):
                    await connection.execute(
                        monitor_sql, {**values, "id": new_id().bytes, "interval": 75}
                    )
                run_sql = text(
                    "INSERT INTO monitor_runs (id,monitor_id,generation,scheduled_for,binding_id,"
                    "credential_version,state,version,attempt_count,execution_epoch) "
                    "VALUES (:run,:id,1,:time,:binding,1,'pending',1,0,1)"
                )
                values.update({"run": new_id().bytes, "time": datetime(2026, 10, 1)})
                await connection.execute(run_sql, values)
                with pytest.raises(DBAPIError):
                    await connection.execute(run_sql, {**values, "run": new_id().bytes})
                sample_sql = text(
                    "INSERT INTO monitor_samples (id,run_id,monitor_id,owner_user_id,binding_id,"
                    "captured_at,balance,quality,credential_version) "
                    "VALUES (:sample,:run,:id,:owner,:binding,:time,25.50,'balance_only',1)"
                )
                await connection.execute(sample_sql, {**values, "sample": new_id().bytes})
                with pytest.raises(DBAPIError):
                    await connection.execute(sample_sql, {**values, "sample": new_id().bytes})
                await connection.rollback()
    finally:
        await engine.dispose()


async def verify_unknown_order_guard(url):
    engine = create_async_engine(url, hide_parameters=True)
    statement = text(
        "INSERT INTO payment_orders (id,owner_user_id,binding_id,binding_display_name,"
        "credential_ref,"
        "credential_version,amount,currency,idempotency_key_hash,request_digest,state,version,"
        "upstream_operation_id) VALUES (:id,:owner,:binding,'synthetic',:credential,1,50.00,'CNY',"
        ":key,:digest,'submit_unknown',1,:upstream)"
    )
    values = {
        "id": new_id().bytes,
        "owner": new_id().bytes,
        "binding": new_id().bytes,
        "credential": new_id().bytes,
        "key": secrets.token_bytes(32),
        "digest": secrets.token_bytes(32),
        "upstream": new_id().bytes,
    }
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(statement, values)
                with pytest.raises(DBAPIError):
                    await connection.execute(
                        statement,
                        {
                            **values,
                            "id": new_id().bytes,
                            "key": secrets.token_bytes(32),
                            "upstream": new_id().bytes,
                        },
                    )
                await connection.rollback()
    finally:
        await engine.dispose()


def test_seven_domains_upgrade_twice_empty_and_least_privilege(tmp_path):
    root_url = make_url(Path(ROOT_SECRET).read_text().strip())
    credentials = asyncio.run(prepare_accounts(root_url, tmp_path))
    for domain in DATABASES:
        environment = {
            **os.environ,
            f"ELECT_{domain.upper()}_DDL_URL_FILE": str(tmp_path / f"{domain}_ddl_url"),
        }
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, "-m", "scripts.migrations", "--domain", domain],
                env=environment,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
    asyncio.run(verify_empty_isolated_databases(root_url, credentials))
    asyncio.run(verify_monitor_constraints(credentials["monitoring"]["app"]))
    asyncio.run(verify_unknown_order_guard(credentials["payment"]["app"]))
