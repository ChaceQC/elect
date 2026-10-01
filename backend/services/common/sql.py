"""本域连接的参数化 SQL 小工具，不持有连接或领域模型。"""

from datetime import UTC

from sqlalchemy import text


async def execute(connection, statement, **params):
    return await connection.execute(text(statement), params)


async def first(connection, statement, **params):
    return (await execute(connection, statement, **params)).mappings().first()


def aware(value):
    return value.replace(tzinfo=UTC) if value is not None else None
