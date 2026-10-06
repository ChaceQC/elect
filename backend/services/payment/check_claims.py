"""回查owner公平游标；owner→操作→订单统一锁序，租约表达跨进程在途。"""

from services.common.ids import new_id
from services.common.read_schedule import claimed
from services.common.sql import execute, first

DUE = (
    "o.next_check_at<=UTC_TIMESTAMP(6) "
    "AND (o.check_lease_until IS NULL OR o.check_lease_until<=UTC_TIMESTAMP(6)) "
    "AND (:order IS NULL OR o.id=:order) "
    "AND (o.cancel_requested_at IS NULL OR o.state='paid_confirmed') "
    "AND (o.state IN ('awaiting_payment','status_unknown','submit_unknown') OR "
    "(o.state='paid_confirmed' AND o.balance_refresh_state='pending'))"
)
IDLE = ("NOT EXISTS(SELECT 1 FROM payment_orders busy WHERE busy.owner_user_id=p.owner_user_id "
        "AND busy.check_lease_until>UTC_TIMESTAMP(6))")


async def claim(engine, order_id=None, schedule=None, *, stop=None):
    params = {"order": order_id.bytes if order_id else None}
    async with engine.connect() as conn:
        owners = (await execute(
            conn, "SELECT p.owner_user_id FROM payment_owners p WHERE " + IDLE + " AND EXISTS("
            "SELECT 1 FROM payment_orders o WHERE o.owner_user_id=p.owner_user_id AND " + DUE + ") "
            "ORDER BY (p.owner_user_id<=:after),p.owner_user_id LIMIT 32",
            **params, after=schedule.after["reconciliation"] if schedule else b"",
        )).scalars().all()
    for owner in owners:
        if stop and stop.is_set():
            return None
        if schedule:
            schedule.visited("reconciliation", owner)
        async with engine.begin() as conn:
            lock = await first(conn, "SELECT owner_user_id FROM payment_owners "
                               "WHERE owner_user_id=:owner FOR UPDATE SKIP LOCKED", owner=owner)
            if not lock or not await first(conn, "SELECT p.owner_user_id FROM payment_owners p "
                                          "WHERE p.owner_user_id=:owner AND " + IDLE, owner=owner):
                continue
            candidate = await first(conn, "SELECT o.id FROM payment_orders o "
                                    "WHERE o.owner_user_id=:owner AND " + DUE +
                                    " ORDER BY o.next_check_at,o.id LIMIT 1", owner=owner, **params)
            if not candidate:
                continue
            await execute(conn, "SELECT id FROM payment_operations WHERE order_id=:id "
                          "FOR UPDATE", id=candidate["id"])
            row = await first(conn, "SELECT o.*,UTC_TIMESTAMP(6) AS claimed_at "
                              "FROM payment_orders o WHERE o.id=:id AND " + DUE + " FOR UPDATE",
                              id=candidate["id"], **params)
            if not row or stop and stop.is_set():
                continue
            lease = str(new_id())
            await execute(conn, "UPDATE payment_orders SET check_lease_owner=:lease,"
                          "check_lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 SECOND) "
                          "WHERE id=:id", lease=lease, id=row["id"])
            claimed("payment", "reconciliation", row, row["next_check_at"])
            return {**row, "check_lease_owner": lease}
    return None
