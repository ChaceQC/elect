"""独立采集周期故障事件，不发送邮件、不使用低余额计数。"""

from services.common.ids import new_id
from services.common.sql import execute


async def cycle_failed(conn, monitor, error):
    cycles = monitor["failed_cycles"] + 1
    await execute(
        conn, "UPDATE monitors SET failed_cycles=:n WHERE id=:id", n=cycles, id=monitor["id"]
    )
    if cycles <= 3:
        return
    await execute(
        conn,
        "INSERT INTO monitor_fault_episodes "
        "(id,monitor_id,opened_at,failed_cycles,last_error_code) "
        "VALUES (:id,:monitor,UTC_TIMESTAMP(6),:n,:error) ON DUPLICATE KEY UPDATE "
        "failed_cycles=:n,last_error_code=:error",
        id=new_id().bytes,
        monitor=monitor["id"],
        n=cycles,
        error=error,
    )


async def cycle_succeeded(conn, monitor):
    await execute(conn, "UPDATE monitors SET failed_cycles=0 WHERE id=:id", id=monitor["id"])
    await execute(
        conn,
        "UPDATE monitor_fault_episodes SET closed_at=UTC_TIMESTAMP(6) "
        "WHERE monitor_id=:id AND closed_at IS NULL",
        id=monitor["id"],
    )
