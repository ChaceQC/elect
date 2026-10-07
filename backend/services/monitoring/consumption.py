"""按采集结束日汇总余额减少估算；读取完整持久基线，不创建明细快照。"""

from services.common.dates import utc_bounds
from services.common.sql import execute

DAILY_SQL = (
    "SELECT DATE(p.captured_at + INTERVAL 8 HOUR) AS record_date,COUNT(*) AS samples,"
    "SUM(CASE WHEN previous.captured_at<p.captured_at AND p.balance<=previous.balance "
    "THEN previous.balance-p.balance ELSE NULL END) AS amount "
    "FROM monitor_samples p LEFT JOIN monitor_samples previous ON "
    "previous.id=p.previous_sample_id AND previous.owner_user_id=p.owner_user_id "
    "AND previous.binding_id=p.binding_id "
    "WHERE p.owner_user_id=:owner AND p.binding_id=:binding "
    "AND p.captured_at>=:start AND p.captured_at<:end "
    "GROUP BY DATE(p.captured_at + INTERVAL 8 HOUR) ORDER BY record_date"
)


async def daily_estimates(engine, owner, command):
    start, end = utc_bounds(command.start_date, command.end_date)
    async with engine.connect() as conn:
        rows = (await execute(
            conn, DAILY_SQL, owner=owner.bytes, binding=command.binding_id.bytes,
            start=start, end=end,
        )).mappings().all()
    return {
        "days": [{"record_date": row["record_date"].isoformat(),
                  "amount": format(row["amount"], ".2f") if row["amount"] is not None else None}
                 for row in rows],
        "sample_count": sum(row["samples"] for row in rows),
    }
