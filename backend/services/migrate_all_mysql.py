"""每域 DDL 账号、同连接 GET_LOCK、可重入 Alembic 升级。"""

import asyncio
import json
import os
import sys

from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.migrations import configuration
from services.common.logging import configure_logging, log
from services.common.migration_runtime import DATABASES
from services.common.runtime import read_secret


def migration_urls():
    document = json.loads(read_secret(os.environ["ELECT_RUNTIME_FILE"]))
    if set(document) != {"domains"} or set(document["domains"]) != set(DATABASES):
        raise ValueError("迁移 Secret 必须覆盖七个领域")
    for domain, raw in document["domains"].items():
        url = make_url(raw)
        short = DATABASES[domain].removeprefix("elect_")
        if (
            url.drivername != "mysql+asyncmy"
            or url.database != DATABASES[domain]
            or url.username != f"elect_{short}_ddl"
        ):
            raise ValueError("迁移须使用本领域 DDL 账号")
    return document["domains"]


async def migrate_domain(domain, url):
    engine = create_async_engine(url, pool_size=1, max_overflow=0, hide_parameters=True)
    lock_name = f"elect:migrate:{domain}"
    try:
        async with engine.connect() as connection:
            locked = (
                await connection.execute(text("SELECT GET_LOCK(:name, 60)"), {"name": lock_name})
            ).scalar()
            if locked != 1:
                raise RuntimeError("迁移锁超时")
            try:
                await connection.execute(text("SET time_zone = '+00:00'"))
                await connection.commit()

                def upgrade(sync_connection):
                    config = configuration(domain)
                    config.attributes["connection"] = sync_connection
                    command.upgrade(config, "head")

                await connection.run_sync(upgrade)
                await connection.commit()
                log("migration_completed", service=domain)
            finally:
                await connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
                await connection.commit()
    finally:
        await engine.dispose()


async def migrate_all():
    for domain, url in migration_urls().items():
        await migrate_domain(domain, url)


def main():
    configure_logging()
    try:
        asyncio.run(migrate_all())
    except Exception:
        log("migration_failed", error_code="MIGRATION_FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
