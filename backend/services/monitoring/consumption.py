"""每日首次余额减少归前一天；先确定归属再过滤日期，不创建明细快照。"""

from datetime import timedelta

from services.common.dates import utc_bounds
from services.common.sql import execute

DAILY_SQL = (
    "WITH observations AS ("
    "SELECT p.id,p.captured_at,DATE(p.captured_at + INTERVAL 8 HOUR) AS capture_date,"
    "CASE WHEN previous.captured_at<p.captured_at AND p.balance<=previous.balance "
    "THEN previous.balance-p.balance ELSE NULL END AS amount "
    "FROM monitor_samples p LEFT JOIN monitor_samples previous ON "
    "previous.id=p.previous_sample_id AND previous.owner_user_id=p.owner_user_id "
    "AND previous.binding_id=p.binding_id "
    "WHERE p.owner_user_id=:owner AND p.binding_id=:binding "
    "AND p.captured_at>=:start AND p.captured_at<:scan_end),"
    "ranked AS (SELECT *,SUM(amount>0) OVER (PARTITION BY capture_date "
    "ORDER BY captured_at,id ROWS UNBOUNDED PRECEDING) AS decrease_no FROM observations),"
    "attributed AS (SELECT CASE WHEN amount>0 AND decrease_no=1 "
    "THEN DATE_SUB(capture_date,INTERVAL 1 DAY) ELSE capture_date END AS record_date,amount "
    "FROM ranked) "
    "SELECT record_date,COUNT(*) AS samples,SUM(amount) AS amount FROM attributed "
    "WHERE record_date BETWEEN :start_date AND :end_date "
    "GROUP BY record_date ORDER BY record_date"
)


async def daily_estimates(engine, owner, command):
    start, end = utc_bounds(command.start_date, command.end_date)
    async with engine.connect() as conn:
        rows = (await execute(
            conn, DAILY_SQL, owner=owner.bytes, binding=command.binding_id.bytes,
            start=start, scan_end=end + timedelta(days=1),
            start_date=command.start_date, end_date=command.end_date,
        )).mappings().all()
    return {
        "days": [{"record_date": row["record_date"].isoformat(),
                  "amount": format(row["amount"], ".2f") if row["amount"] is not None else None}
                 for row in rows],
        "sample_count": sum(row["samples"] for row in rows),
    }
