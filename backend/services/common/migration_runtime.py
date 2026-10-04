"""各库独立迁移的连接设施；不含共享领域 ORM/仓储。"""

import asyncio
import os
from pathlib import Path

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from .domains import DATABASES


def configure_connection(connection):
    context.configure(connection=connection, target_metadata=None, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online(domain: str):
    key = f"ELECT_{domain.upper()}_DDL_URL_FILE"
    path = os.environ.get(key)
    if not path:
        raise RuntimeError(f"迁移需要 Secret 文件变量 {key}")
    url = make_url(Path(path).read_text().strip())
    if url.drivername != "mysql+asyncmy" or url.database != DATABASES[domain]:
        raise RuntimeError("迁移连接必须是本领域的 mysql+asyncmy 数据库")
    engine = create_async_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET time_zone = '+00:00'"))
            await connection.commit()
            await connection.run_sync(configure_connection)
    finally:
        await engine.dispose()


def run(domain: str):
    existing = context.config.attributes.get("connection")
    if existing is not None:
        configure_connection(existing)
    elif context.is_offline_mode():
        context.configure(
            url=f"mysql+asyncmy://offline/{DATABASES[domain]}",
            target_metadata=None,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        asyncio.run(online(domain))
