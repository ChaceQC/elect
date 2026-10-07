"""固定10账号混合场景准备和只读终态计数；仅供隔离集成脚本。"""

from uuid import UUID

from scripts.t4_monitor_smoke import enable, run_request
from scripts.t5_alert_smoke import collect
from scripts.t6_smoke import account, create
from services.common.dates import today
from services.common.ids import new_id
from services.common.sql import execute, first
from services.payment.worker import worker_tick


async def prepare(apps, school):
    clients, owners, runs, histories, orders = [], [], [], [], []
    for _ in range(10):
        client, user, binding = await account(apps, school)
        clients.append(client)
        owner = UUID(user["id"])
        owners.append(owner.bytes)
        await enable(client)
        await collect(apps["monitoring"].state.database, owner, "19.99")
        # 真实快照API固定已有样本成员，之后只令本场景快照过期。
        response = await client.get(f"/api/v1/room-bindings/{binding}/monitor-samples",
                                   params={"start_date": today().isoformat(),
                                           "end_date": today().isoformat()})
        assert response.status_code == 200
        runs.append((await run_request(client)).bytes)
        response = await client.post(f"/api/v1/room-bindings/{binding}/history-sync",
            headers={"Idempotency-Key": str(new_id())},
            json={"start_date": "2026-09-01", "end_date": "2026-09-14"})
        assert response.status_code == 202
        histories.append(UUID(response.json()["data"]["operation_id"]).bytes)
        response = await create(client, binding)
        assert response.status_code == 202
        order = UUID(response.json()["data"]["order_id"])
        assert await worker_tick(apps["payment"], order_id=order)
        orders.append(order.bytes)
    params = {f"o{i}": owner for i, owner in enumerate(owners)}
    ids = ",".join(f":{key}" for key in params)
    async with apps["monitoring"].state.database.begin() as conn:
        await execute(conn, "UPDATE sample_snapshots SET expires_at='2000-01-01' "
                      f"WHERE owner_user_id IN ({ids})", **params)
    async with apps["payment"].state.database.begin() as conn:
        await execute(conn, "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6),"
                      f"last_checked_at=NULL WHERE owner_user_id IN ({ids})", **params)
    return clients, owners, runs, histories, orders


async def counts(apps, data):
    _, owners, runs, histories, orders = data
    queries = [("monitoring", "monitor_runs", "id", runs, "state='succeeded'"),
               ("room", "room_operations", "id", histories, "state='succeeded'"),
               ("payment", "payment_orders", "id", orders, "last_checked_at IS NOT NULL"),
               ("monitoring", "sample_snapshots", "owner_user_id", owners, "1=1")]
    result = []
    for domain, table, key, values, condition in queries:
        params = {f"v{i}": value for i, value in enumerate(values)}
        ids = ",".join(f":{name}" for name in params)
        async with apps[domain].state.database.connect() as conn:
            result.append((await first(conn, f"SELECT COUNT(*) AS n FROM {table} "
                f"WHERE {key} IN ({ids}) AND {condition}", **params))["n"])
    return result


async def stop_synthetic_work(apps, owners):
    params = {f"v{i}": value for i, value in enumerate(owners)}
    ids = ",".join(f":{key}" for key in params)
    async with apps["payment"].state.database.begin() as conn:
        await execute(conn, f"UPDATE payment_orders SET next_check_at=NULL "
                      f"WHERE owner_user_id IN ({ids})", **params)
    async with apps["monitoring"].state.database.begin() as conn:
        await execute(conn, "UPDATE monitors SET desired_enabled=0,state='disabled',"
                      f"next_run_at=NULL WHERE owner_user_id IN ({ids})", **params)
