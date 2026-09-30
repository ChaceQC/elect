"""有上限的本域数据库连接池；数据库会话固定 UTC。"""

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine


def create_database(url):
    engine = create_async_engine(
        url,
        pool_size=2,
        max_overflow=3,
        pool_timeout=3,
        pool_recycle=1800,
        pool_pre_ping=True,
        hide_parameters=True,
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
