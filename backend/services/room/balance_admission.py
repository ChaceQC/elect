"""余额新键预算；所有绑定共享owner额度，系统待办独立有界。"""

from services.common.admission import enforce_budget
from services.common.sql import first


async def check_budget(conn, owner, source):
    recent = await first(
        conn, "SELECT COUNT(*) AS daily,COALESCE(SUM(created_at>"
        "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 MINUTE)),0) AS minute,"
        "MIN(created_at) AS earliest,UTC_TIMESTAMP(6) AS now FROM room_operations "
        "WHERE owner_user_id=:owner AND type='balance_refresh' AND request_source=:source "
        "AND created_at>DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 DAY)",
        owner=owner.bytes, source=source,
    )
    pending = await first(
        conn, "SELECT COUNT(*) AS n FROM room_operations WHERE owner_user_id=:owner "
        "AND type='balance_refresh' AND request_source=:source "
        "AND state IN ('accepted','running','reconciling','unknown')",
        owner=owner.bytes, source=source,
    )
    # 系统与浏览器分别6/60/8；订单固定键重放不计数。
    enforce_budget(recent, pending["n"])
