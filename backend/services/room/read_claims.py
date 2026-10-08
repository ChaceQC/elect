"""读取先选有工作的owner，再按偏好→任务加锁；无在途账号排队。"""

from services.common.ids import new_id
from services.common.read_schedule import claimed
from services.common.sql import execute, first

OP_DUE = {
    "binding_sync": "o.type='binding_sync' AND (o.state='accepted' OR "
                    "(o.state='running' AND o.lease_until<=UTC_TIMESTAMP(6)))",
    "balance_refresh": "o.type='balance_refresh' AND "
                       "(o.saga_step<>'merged' OR o.request_source='payment') "
                       "AND o.state IN ('accepted','running') AND "
                       "(o.lease_until IS NULL OR o.lease_until<=UTC_TIMESTAMP(6))",
}
HISTORY_DUE = (
    "s.status IN ('accepted','running') AND ((w.state IN ('pending','retry_wait') "
    "AND w.next_attempt_at<=UTC_TIMESTAMP(6)) OR "
    "(w.state='running' AND w.lease_until<=UTC_TIMESTAMP(6)))"
)
IDLE = (
    "NOT EXISTS(SELECT 1 FROM room_operations active WHERE active.owner_user_id=p.owner_user_id "
    "AND active.type IN ('binding_sync','balance_refresh') AND active.state='running' "
    "AND active.lease_until>UTC_TIMESTAMP(6)) AND NOT EXISTS(SELECT 1 FROM history_syncs s "
    "JOIN history_sync_windows w ON w.sync_id=s.id WHERE s.owner_user_id=p.owner_user_id "
    "AND w.state='running' AND w.lease_until>UTC_TIMESTAMP(6))"
)


async def candidates(engine, kind, schedule=None):
    due = ("SELECT 1 FROM history_syncs s JOIN history_sync_windows w ON w.sync_id=s.id "
           "WHERE s.owner_user_id=p.owner_user_id AND " + HISTORY_DUE
           if kind == "history_sync" else
           "SELECT 1 FROM room_operations o WHERE o.owner_user_id=p.owner_user_id AND "
           + OP_DUE[kind])
    async with engine.connect() as conn:
        return (await execute(
            conn, "SELECT p.owner_user_id FROM room_preferences p WHERE EXISTS(" + due + ") "
            "AND " + IDLE + " ORDER BY (p.owner_user_id<=:after),p.owner_user_id LIMIT 32",
            after=schedule.after[kind] if schedule else b"",
        )).scalars().all()


async def lock_idle(conn, owner):
    # 领取从不插入owner行；受理入口已保证存在。锁忙立即跳过，不占执行槽等账号。
    row = await first(conn, "SELECT owner_user_id FROM room_preferences "
                      "WHERE owner_user_id=:owner FOR UPDATE SKIP LOCKED", owner=owner)
    if not row:
        return False
    return bool(await first(conn, "SELECT p.owner_user_id FROM room_preferences p "
                            "WHERE p.owner_user_id=:owner AND " + IDLE, owner=owner))


async def claim_operation(engine, kind, schedule=None, *, stop=None):
    for owner in await candidates(engine, kind, schedule):
        if stop and stop.is_set():
            return None
        if schedule:
            schedule.visited(kind, owner)
        async with engine.begin() as conn:
            if not await lock_idle(conn, owner):
                continue
            row = await first(
                conn, "SELECT o.*,UTC_TIMESTAMP(6) AS claimed_at FROM room_operations o "
                "WHERE o.owner_user_id=:owner AND " + OP_DUE[kind] +
                " ORDER BY o.created_at,o.id LIMIT 1 FOR UPDATE", owner=owner,
            )
            if not row or stop and stop.is_set():
                continue
            if kind == "balance_refresh" and row["saga_step"] == "merged":
                # 旧版本未终结的支付别名改为独立读取；不复用付款前的根结果。
                await execute(conn, "UPDATE room_operations SET saga_step='read_school',"
                              "upstream_operation_id=NULL WHERE id=:id", id=row["id"])
                row = {**row, "saga_step": "read_school", "upstream_operation_id": None}
            lease = str(new_id())
            await execute(conn, "UPDATE room_operations SET state='running',lease_owner=:lease,"
                          "lease_until=TIMESTAMPADD(SECOND,:seconds,UTC_TIMESTAMP(6)),"
                          "updated_at=UTC_TIMESTAMP(6) WHERE id=:id", lease=lease, id=row["id"],
                          seconds=120 if kind == "binding_sync" else 45)
            claimed("room", kind, row, row["created_at"])
            return {**row, "lease_owner": lease}
    return None
