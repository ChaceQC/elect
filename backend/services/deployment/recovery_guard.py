"""受限运维作业：数据清点、空库门禁与可重入恢复隔离；不访问学校/MQ/SMTP。"""

import argparse
import asyncio
import json
import os
import re

from sqlalchemy.ext.asyncio import create_async_engine

from services.common.sql import execute, first
from services.migrate_all_mysql import migration_urls

from .recovery_rules import OUTBOX_HOLD, RULES


async def inventory(conn):
    rows = (await execute(
        conn, "SELECT table_name AS name FROM information_schema.tables "
        "WHERE table_schema=DATABASE() AND table_type='BASE TABLE' ORDER BY table_name",
    )).mappings().all()
    counts = {}
    for row in rows:
        name = row["name"]
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
            raise ValueError("数据库表名不受支持")
        counts[name] = (await first(conn, f"SELECT COUNT(*) AS n FROM `{name}`"))["n"]
    revision = await first(conn, "SELECT version_num FROM alembic_version")
    return {"revision": revision["version_num"], "tables": counts}


async def run(mode):
    if mode != "inventory" and os.environ.get("ELECT_RECOVERY_ISOLATED") != "1":
        raise ValueError("恢复操作必须显式使用隔离覆盖配置")
    result = {}
    for domain, url in migration_urls().items():
        engine = create_async_engine(
            url, pool_size=1, max_overflow=0, hide_parameters=True,
            isolation_level="READ COMMITTED",
        )
        try:
            async with engine.begin() as conn:
                await execute(conn, "SET time_zone='+00:00'")
                if mode == "apply":
                    from services.common.archive_verify import verify_archives, verify_cold_links

                    await verify_archives(conn)
                    await verify_cold_links(conn)
                    # 每域独立事务；网络隔离和停止Worker先行，部分失败可安全重入。
                    for statement in RULES.get(domain, []):
                        await execute(conn, statement)
                    exists = await first(
                        conn, "SELECT COUNT(*) AS n FROM information_schema.tables "
                        "WHERE table_schema=DATABASE() AND table_name='outbox_events'",
                    )
                    if exists["n"]:
                        await execute(conn, OUTBOX_HOLD)
                value = await inventory(conn)
                if mode == "require-empty" and any(
                    count for table, count in value["tables"].items() if table != "alembic_version"
                ):
                    raise ValueError("恢复目标含业务记录，拒绝覆盖")
                result[domain] = value
        finally:
            await engine.dispose()
    return {"mode": mode, "domains": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["inventory", "require-empty", "apply"])
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args.mode))))
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback
            from pathlib import Path

            print(type(error).__name__)
            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit("恢复门禁失败：检查隔离配置、空库、结构版本或领域连接") from None


if __name__ == "__main__":
    main()
