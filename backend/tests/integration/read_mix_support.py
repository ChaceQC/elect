"""50个合成账号、两个真实领域池的单槽/双槽固定对照。"""

import asyncio
from time import perf_counter
from types import SimpleNamespace
from uuid import UUID

from query_resource_support import seed_binding
from sqlalchemy import event
from test_history_admission import accept
from test_payment_polling import seed

from services.common.heartbeat import Heartbeat
from services.common.ids import new_id
from services.common.read_schedule import ReadSchedule
from services.common.sql import execute, first
from services.payment.process import role_loop, scan_loop
from services.room.balance import accept_refresh, get_balance
from services.room.read_loop import room_loop, slot_loop
from services.room.repository import RoomRepository


async def prepare(room, payment):
    owners, bindings, rooms, orders = [], {}, {}, {}
    for index in range(1, 51):
        owner, binding = UUID(int=index), new_id()
        owners.append(owner)
        bindings[owner] = binding
        await seed_binding(room, owner, binding)
        if index % 3 == 1:
            await RoomRepository(room).accept_sync(owner, str(new_id()))
        elif index % 3 == 2:
            await accept_refresh(room, owner, binding, str(new_id()))
        else:
            await accept(room, owner, binding)
        order, previous = await seed(payment)
        orders[owner] = order
        async with payment.begin() as conn:
            await execute(conn, "UPDATE payment_owners SET owner_user_id=:owner "
                          "WHERE owner_user_id=:old", owner=owner.bytes, old=previous.bytes)
            for table in ("payment_orders", "payment_operations"):
                await execute(conn, f"UPDATE {table} SET owner_user_id=:owner "
                              "WHERE owner_user_id=:old", owner=owner.bytes, old=previous.bytes)
        async with room.connect() as conn:
            row = await first(conn, "SELECT r.school_room_id FROM rooms r JOIN room_bindings b "
                              "ON b.room_id=r.id WHERE b.id=:id", id=binding.bytes)
            rooms[owner] = row["school_room_id"]
    return owners, bindings, rooms, orders


async def scenario(room, payment, slots):
    owners, bindings, rooms, orders = await prepare(room, payment)
    stop = asyncio.Event()
    active, peak, calls, first_fast = {}, {"room": 0, "payment": 0}, [], {}
    read_times, pool_peak, renewals = [], {"room": 0, "payment": 0}, []
    slow_room_heartbeat = []
    started = perf_counter()

    def observe(conn, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE payment_orders SET check_lease_until="):
            renewals.append(1)

    event.listen(payment.sync_engine, "before_cursor_execute", observe)

    def client(domain):
        async def call(service, path, *args, principal, **kwargs):
            owner = principal.user_id
            key = domain, owner
            assert key not in active  # 不允许同owner占用两个槽或跨Room种类重入。
            active[key] = True
            peak[domain] = max(peak[domain], sum(k[0] == domain for k in active))
            assert peak[domain] <= slots
            if owner != owners[0]:
                first_fast.setdefault(domain, perf_counter() - started)
            try:
                await asyncio.sleep(11 if owner == owners[0] else .01)
                calls.append(key)
                if domain == "payment":
                    return {"order_state": "expired_confirmed"}
                if path == "/queries/history":
                    return {"items": [], "request_room_id": rooms[owner]}
                return {"items": [] if owner.int % 3 == 1 else [
                    {"room_id": rooms[owner], "balance": "25.50"}]}
            finally:
                del active[key]
        return SimpleNamespace(call=call)

    app_room = SimpleNamespace(state=SimpleNamespace(database=room, service_client=client("room"),
        history_reconnect_at=float("inf"), read_wakeup_lock=asyncio.Lock(),
        read_schedule=ReadSchedule(("binding_sync", "balance_refresh", "history_sync"))))
    app_pay = SimpleNamespace(state=SimpleNamespace(
        database=payment, service_client=client("payment")))
    beats = Heartbeat("room", "worker"), Heartbeat("payment", "reconciliation")

    async def sample():
        while len(calls) < 100:
            start = perf_counter()
            await get_balance(room, owners[1], bindings[owners[1]])
            async with room.begin() as conn:
                await execute(conn, "SELECT owner_user_id FROM room_preferences "
                              "WHERE owner_user_id=:owner FOR UPDATE", owner=owners[-1].bytes)
            async with payment.connect() as conn:
                await first(conn, "SELECT state FROM payment_orders WHERE id=:id",
                            id=orders[owners[1]].bytes)
            read_times.append(perf_counter() - start)
            if 10.3 < perf_counter() - started < 10.8 and ("room", owners[0]) in active:
                current = beats[0].snapshot()
                slots = current.get("slots", {"only": current})
                slow_room_heartbeat.append(any(
                    slot["inflight"] and any(
                        slot["last_tick"] - work["started_at"] >= 9
                        for work in slot["inflight"].values())
                    for slot in slots.values()))
            for domain, engine in (("room", room), ("payment", payment)):
                pool_peak[domain] = max(pool_peak[domain], engine.pool.checkedout())
                assert engine.pool.size() == 2 and engine.pool._max_overflow == 1
            await asyncio.sleep(.02)
        stop.set()

    try:
        async with asyncio.timeout(40):
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(room_loop(app_room, stop, beats[0]) if slots == 2 else
                                  slot_loop(app_room, stop, beats[0], None))
                tasks.create_task(role_loop("reconciliation", app_pay, stop, beats[1]) if slots == 2
                                  else scan_loop("reconciliation", app_pay, stop, beats[1]))
                tasks.create_task(sample())
    finally:
        stop.set()
        event.remove(payment.sync_engine, "before_cursor_execute", observe)
    assert len(calls) == len(set(calls)) == 100 and len(renewals) >= 1
    assert slow_room_heartbeat and all(slow_room_heartbeat)
    for domain, engine in (("room", room), ("payment", payment)):
        table = "room_operations" if domain == "room" else "payment_orders"
        condition = ("state IN ('accepted','running')" if domain == "room"
                     else "next_check_at IS NOT NULL")
        async with engine.connect() as conn:
            pending = await first(conn, f"SELECT COUNT(*) AS n FROM {table} WHERE {condition}")
            assert not pending["n"]
    assert all(beat.snapshot()["failures"] == 0 for beat in beats)
    return {"seconds": round(perf_counter() - started, 3), "first_fast": first_fast,
            "read_p95_ms": round(sorted(read_times)[int(len(read_times) * .95)] * 1000, 2),
            "calls": len(calls), "peak_slots": peak, "pool_sample_peak": pool_peak,
            "renewals": len(renewals), "slow_room_heartbeat": True, "failures": 0}
