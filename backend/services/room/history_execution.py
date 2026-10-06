"""一个窗口一个90秒预算；独立续租直到提交持有行锁，失租拒绝迟到执行。"""

import asyncio
from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first

from .history_store import finish_history

LEASE_SECONDS = 45
RENEW_SECONDS = 10
EXECUTION_SECONDS = 90


async def renew(engine, row):
    async with engine.begin() as conn:
        current = await first(
            conn, "SELECT w.* FROM history_sync_windows w JOIN history_syncs s ON s.id=w.sync_id "
            "WHERE w.id=:id AND s.owner_user_id=:owner FOR UPDATE",
            id=row["id"], owner=row["owner_user_id"],
        )
        now = (await first(conn, "SELECT UTC_TIMESTAMP(6) AS now"))["now"]
        if (not current or current["state"] != "running"
                or current["lease_owner"] != row["lease_owner"]
                or current["execution_epoch"] != row["execution_epoch"]
                or not current["lease_until"] or current["lease_until"] <= now):
            return False
        result = await execute(
            conn, "UPDATE history_sync_windows w JOIN history_syncs s ON s.id=w.sync_id "
            "SET w.lease_until=TIMESTAMPADD(SECOND,:seconds,UTC_TIMESTAMP(6)) "
            "WHERE w.id=:id AND s.owner_user_id=:owner AND w.state='running' "
            "AND w.lease_owner=:lease AND w.execution_epoch=:epoch "
            "AND w.lease_until>UTC_TIMESTAMP(6)",
            id=row["id"], owner=row["owner_user_id"], lease=row["lease_owner"],
            epoch=row["execution_epoch"], seconds=LEASE_SECONDS,
        )
    return bool(result.rowcount)


async def execute_window(app, row, *, heartbeat=None):
    committing = asyncio.Event()
    deadline = asyncio.get_running_loop().time() + EXECUTION_SECONDS

    async def work():
        principal = Principal("room", UUID(bytes=row["owner_user_id"]), 1, new_id())
        async with asyncio.timeout_at(deadline):
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                value = await app.state.service_client.call(
                    "school_adapter", "/queries/history", "school:history", principal.request_id,
                    {"binding_id": str(UUID(bytes=row["binding_id"])),
                     "start_date": row["start_date"].isoformat(),
                     "end_date": row["end_date"].isoformat(), "budget_seconds": remaining},
                    principal=principal, budget=remaining,
                )
                error, retryable, retry_after = None, False, None
            except ApiError as failure:
                value, error, retryable = None, failure.code, failure.retryable
                retry_after = failure.retry_after_seconds
            return await finish_history(app.state.database, row, value, error, retryable,
                                        retry_after, committing=committing)

    async def lease_loop():
        while True:
            await asyncio.sleep(RENEW_SECONDS)
            if committing.is_set():
                continue  # 最终事务持有窗口行锁；事务完成前不能被新领取者接管。
            if not await renew(app.state.database, row):
                return False
            if heartbeat:
                heartbeat.write(healthy=True)

    task, lease = asyncio.create_task(work()), asyncio.create_task(lease_loop())
    try:
        done, _ = await asyncio.wait({task, lease}, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            try:
                return task.result()
            except TimeoutError:
                # 完整预算已消耗，不另开事务续命；租约到期后按原三次上限接管。
                return False
        lease.result()  # 续租异常同样取消执行，留持久租约恢复。
        return False
    finally:
        for pending in (task, lease):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, lease, return_exceptions=True)
