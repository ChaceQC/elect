"""实际数据库的取消幂等、归属、占位释放和迟到执行检查。"""

from types import SimpleNamespace
from uuid import UUID

from scripts.t6_smoke import account, create, read
from services.common.ids import new_id
from services.common.sql import execute, first
from services.payment.cancellation import settle_cancellations
from services.payment.jobs import claim, dispatch_proof, update
from services.payment.worker import worker_tick


async def cancel(client, order, version):
    return await client.post(
        f"/api/v1/payment-orders/{order}/cancel", json={"expected_version": version}
    )


async def verify_cancellation(apps, school):
    client, user, binding = await account(apps, school)
    other, _, _ = await account(apps, school)
    engine = apps["payment"].state.database
    try:
        initial = school.payment_posts["D01"]
        key = str(new_id())
        accepted = await create(client, binding, "1.00", key)
        order = accepted.json()["data"]["order_id"]
        current = await read(client, order)
        assert (await cancel(other, order, current["version"])).status_code == 404
        missing = await client.post(f"/api/v1/payment-orders/{order}/cancel", json={})
        assert missing.status_code == 428
        assert (await cancel(client, order, current["version"] + 1)).status_code == 409
        blocked = await client.post(
            f"/api/v1/payment-orders/{order}/cancel",
            json={"expected_version": current["version"]}, headers={"X-CSRF-Token": "wrong"},
        )
        assert blocked.status_code == 403
        response = await cancel(client, order, current["version"])
        assert response.status_code == 200 and response.json()["data"]["cancelled_at"]
        repeated = await cancel(client, order, current["version"])
        assert repeated.json()["data"]["cancelled_at"] == response.json()["data"]["cancelled_at"]
        replay = await create(client, binding, "1.00", key)
        assert replay.json()["data"]["order_id"] == order
        assert not await worker_tick(apps["payment"], order_id=UUID(order))
        assert school.payment_posts["D01"] == initial
        print("创建前取消、重复取消/原键保留、缺版本/冲突/CSRF/跨用户拒绝：通过")

        pending = (await create(client, binding, "1.00")).json()["data"]["order_id"]
        await worker_tick(apps["payment"], order_id=UUID(pending))
        current = await read(client, pending)
        assert current["qr_status"] == "ready"
        before = school.payment_posts.copy()
        assert (await cancel(client, pending, current["version"])).json()["data"]["cancelled_at"]
        assert (await client.get(f"/api/v1/payment-orders/{pending}/qr")).status_code == 409
        assert (await client.post(
            f"/api/v1/payment-orders/{pending}/qr-refresh",
            headers={"Idempotency-Key": str(new_id())},
        )).status_code == 409
        assert school.payment_posts == before
        async with apps["school_adapter"].state.database.connect() as conn:
            upstream = await first(
                conn, "SELECT u.dispatched_at FROM adapter_payment_orders p "
                "JOIN upstream_operations u ON u.id=p.upstream_operation_id WHERE p.order_id=:id",
                id=UUID(pending).bytes,
            )
        assert upstream["dispatched_at"]
        print("二维码就绪后取消释放占位、阻止图片/刷新、学校永久发送台账保留：通过")

        active = (await create(client, binding, "1.00")).json()["data"]["order_id"]
        old = await claim(engine, UUID(active))
        current = await read(client, active)
        result = (await cancel(client, active, current["version"])).json()["data"]
        assert result["cancel_pending"] and not result["cancelled_at"]
        assert (await create(client, binding)).status_code == 409
        assert not await update(engine, old, order_state="awaiting_payment")
        proof = await dispatch_proof(
            engine, UUID(user["id"]), SimpleNamespace(
                order_id=UUID(active), operation_id=UUID(bytes=old["operation_id"]),
                lease_owner=old["lease_owner"],
            ),
        )
        assert not proof["can_dispatch"]
        async with engine.begin() as conn:
            await execute(
                conn, "UPDATE payment_orders SET cancel_after=DATE_SUB(UTC_TIMESTAMP(6),"
                "INTERVAL 1 SECOND) WHERE id=:id", id=UUID(active).bytes,
            )
        assert await settle_cancellations(engine)
        assert (await read(client, active))["cancelled_at"]
        newest = (await create(client, binding)).json()["data"]["order_id"]
        async with engine.begin() as conn:
            await execute(
                conn, "UPDATE payment_orders SET state='paid_confirmed' WHERE id=:id",
                id=UUID(newest).bytes,
            )
        current = await read(client, newest)
        assert (await cancel(client, newest, current["version"])).status_code == 409
        print("在途取消暂占位、旧epoch/新dispatch拒绝、恢复释放、已确认支付禁止取消：通过")
    finally:
        await client.aclose()
        await other.aclose()
