"""受限Docker运维入口：聚合积压/未知/连接与数据规模，不含账户或敏感载荷。"""

import asyncio
import json

from sqlalchemy.ext.asyncio import create_async_engine

from services.common.sql import execute, first
from services.migrate_all_mysql import migration_urls

COUNTERS = {
    "identity": ("SELECT COUNT(*) AS requires_reauth FROM users "
                 "WHERE credential_status='requires_reauth'"),
    "school_adapter": ("SELECT COUNT(*) AS upstream_unknown FROM upstream_operations "
                       "WHERE state IN ('dispatched','reconciling','unknown')"),
    "room": ("SELECT COUNT(*) AS unknown_operations FROM room_operations "
             "WHERE state IN ('reconciling','unknown')"),
    "monitoring": ("SELECT COUNT(*) AS active_plans,MAX(GREATEST(0,"
                   "TIMESTAMPDIFF(SECOND,next_run_at,UTC_TIMESTAMP(6)))) AS schedule_lag_seconds "
                   "FROM monitors WHERE state='active' AND desired_enabled=1"),
    "notification": ("SELECT state,COUNT(*) AS n FROM notification_jobs GROUP BY state"),
    "payment": ("SELECT state,COUNT(*) AS n FROM payment_orders GROUP BY state"),
}


async def collect():
    result = {}
    for domain, url in migration_urls().items():
        engine = create_async_engine(url, pool_size=1, max_overflow=0, hide_parameters=True)
        try:
            async with engine.connect() as conn:
                revision = await first(conn, "SELECT version_num FROM alembic_version")
                value = {"revision": revision["version_num"]}
                value["outbox"] = dict(await first(
                    conn, "SELECT COUNT(*) AS unpublished,"
                    "SUM(available_at>='9999-01-01') AS quarantined,"
                    "MAX(CASE WHEN available_at<=UTC_TIMESTAMP(6) THEN "
                    "TIMESTAMPDIFF(SECOND,available_at,UTC_TIMESTAMP(6)) END) "
                    "AS oldest_due_seconds "
                    "FROM outbox_events WHERE published_at IS NULL",
                ))
                value["outbox"] = {key: int(number) if number is not None else None
                                   for key, number in value["outbox"].items()}
                if domain in COUNTERS:
                    rows = (await execute(conn, COUNTERS[domain])).mappings().all()
                    value["business"] = [dict(row) for row in rows]
                if domain == "monitoring":
                    value["runs"] = [dict(row) for row in (await execute(
                        conn, "SELECT state,COUNT(*) AS n FROM monitor_runs GROUP BY state",
                    )).mappings().all()]
                if domain == "identity":
                    rows = (await execute(
                        conn, "SHOW GLOBAL STATUS WHERE Variable_name IN "
                        "('Threads_connected','Max_used_connections','Slow_queries')",
                    )).mappings().all()
                    value["mysql"] = {row["Variable_name"]: int(row["Value"]) for row in rows}
                    value["mysql"]["max_connections"] = (await first(
                        conn, "SELECT @@max_connections AS n",
                    ))["n"]
                size = (await first(
                    conn, "SELECT SUM(data_length+index_length) AS n "
                    "FROM information_schema.tables "
                    "WHERE table_schema=DATABASE()",
                ))["n"]
                value["allocated_table_bytes"] = int(size) if size is not None else None
                result[domain] = value
        finally:
            await engine.dispose()
    return {"domains": result, "contains_account_labels": False}


def main():
    try:
        print(json.dumps(asyncio.run(collect()), default=str))
    except Exception:
        raise SystemExit("运行状态读取失败：检查领域运行配置和结构") from None


if __name__ == "__main__":
    main()
