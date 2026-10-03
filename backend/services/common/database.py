"""有上限的本域数据库连接池；数据库会话固定 UTC。"""

import os

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine


def migration_head(domain):
    from alembic.script import ScriptDirectory

    from scripts.migrations import configuration

    return ScriptDirectory.from_config(configuration(domain)).get_current_head()


def pool_options():
    try:
        size = int(os.environ.get("ELECT_DB_POOL_SIZE", "2"))
        overflow = int(os.environ.get("ELECT_DB_MAX_OVERFLOW", "3"))
        if not 1 <= size <= 10 or not 0 <= overflow <= 10:
            raise ValueError()
    except ValueError:
        raise RuntimeError("数据库连接池配置无效：基础连接1..10，溢出连接0..10") from None
    return {"pool_size": size, "max_overflow": overflow}


def create_database(url):
    engine = create_async_engine(
        url,
        connect_args={"connect_timeout": 3},
        **pool_options(),
        pool_timeout=3,
        pool_recycle=1800,
        pool_pre_ping=True,
        hide_parameters=True,
        isolation_level="READ COMMITTED",
    )

    @event.listens_for(engine.sync_engine, "connect")
    def utc_connection(connection, record):
        cursor = connection.cursor()
        cursor.execute("SET time_zone = '+00:00'")
        cursor.close()

    return engine


async def database_ready(engine, expected_revision):
    async with engine.connect() as connection:
        actual = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar()
        if actual != expected_revision:
            raise RuntimeError("迁移版本未就绪")
