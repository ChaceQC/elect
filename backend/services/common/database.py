"""有上限的本域数据库连接池；数据库会话固定 UTC。"""

import json
import os
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .scheduling import Wakeup

OUTBOX_PENDING = "elect_outbox_pending"


class DomainEngine(AsyncEngine):
    """保持AsyncEngine接口，仅在完整事务成功提交后发本进程提示。"""

    def __init__(self, sync_engine):
        super().__init__(sync_engine)
        self.outbox_wakeup = Wakeup()

    @asynccontextmanager
    async def begin(self):
        pending = False
        async with super().begin() as connection:
            info = connection.info
            info.pop(OUTBOX_PENDING, None)
            try:
                yield connection
            finally:
                # 池归还前清除连接局部标记；回滚/取消/提交失败不进入下面的提示。
                pending = info.pop(OUTBOX_PENDING, False)
        if pending:
            self.outbox_wakeup.set()


@cache
def migration_head(domain):
    from .domains import DATABASES

    heads = json.loads(Path(__file__).with_name("migration_heads.json").read_text(encoding="utf-8"))
    if set(heads) != set(DATABASES) or not all(isinstance(v, str) and v for v in heads.values()):
        raise RuntimeError("构建迁移版本清单无效")
    return heads[domain]


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

    return DomainEngine(engine.sync_engine)


async def database_ready(engine, expected_revision):
    async with engine.connect() as connection:
        actual = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar()
        if actual != expected_revision:
            raise RuntimeError("迁移版本未就绪")
