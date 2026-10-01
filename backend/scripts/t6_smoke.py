"""真实 MySQL/Redis + 合成学校；不执行任何真实订单或付款。"""

import asyncio
import os
from uuid import UUID

import httpx

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t6_fixtures import PaymentSchool
from services.common.config_contract import SideEffectPolicy
from services.common.ids import new_id
from services.common.sql import execute, first
from services.payment.worker import worker_tick
from services.room.worker import sync_tick
from services.school_adapter.infrastructure.payment_transport import PaymentTransport


async def account(apps, school):
    client = browser(apps["gateway"])
    name = f"synthetic-payment-{new_id()}"
    school.bindings[name] = [{**school.rooms["synthetic-room-402"], "bruId": "synthetic-relation"}]
    user = await login(client, await prepare(client, name))
    apps["payment"].state.test_owners = [
        *getattr(apps["payment"].state, "test_owners", []),
        UUID(user["id"]),
    ]
    response = await client.post(
        "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
    )
    assert response.status_code == 202
    for _ in range(20):
        await sync_tick(apps["room"])
        bindings = (await client.get("/api/v1/room-bindings")).json()["data"]
        if bindings["items"]:
            return client, user, bindings["items"][0]["id"]
    raise AssertionError("合成绑定未同步")


async def create(client, binding, amount="20.00", key=None):
    return await client.post(
        "/api/v1/payment-orders",
        headers={"Idempotency-Key": key or str(new_id())},
        json={"binding_id": binding, "amount": amount},
    )


async def read(client, order):
    response = await client.get(f"/api/v1/payment-orders/{order}")
    assert response.status_code == 200, response.status_code
    assert (
        "prePayId" not in response.text
        and "pay_url" not in response.text
        and "__VIEWSTATE" not in response.text
    )
    return response.json()["data"]


async def due(app, order):
    async with app.state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE payment_operations SET next_attempt_at=UTC_TIMESTAMP(6) WHERE order_id=:id",
            id=UUID(order).bytes,
        )
        await execute(
            conn,
            "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=UUID(order).bytes,
        )


async def basic(apps, school):
    client, user, binding = await account(apps, school)
    other, _, other_binding = await account(apps, school)
    try:
        apps["payment"].state.side_effect_policy = SideEffectPolicy()
        capabilities = (
            await client.get(f"/api/v1/payments/capabilities?binding_id={binding}")
        ).json()["data"]
        assert not capabilities["enabled"] and capabilities["amount_step"] == "1.00"
        assert (await create(client, binding)).status_code == 403
        apps["payment"].state.side_effect_policy = apps["school_adapter"].state.side_effect_policy
        assert (await create(client, binding, "1.01")).status_code == 422
        assert (await create(client, other_binding)).status_code == 404
        key = str(new_id())
        results = await asyncio.gather(*(create(client, binding, key=key) for _ in range(5)))
        assert all(value.status_code == 202 for value in results), [
            value.status_code for value in results
        ]
        order = results[0].json()["data"]["order_id"]
        assert {value.json()["data"]["order_id"] for value in results} == {order}
        assert (await create(client, binding, "21.00", key)).status_code == 409
        conflict = await create(client, binding)
        assert (
            conflict.status_code == 409
            and conflict.json()["error"]["existing_operation_id"] == order
        )
        assert (await other.get(f"/api/v1/payment-orders/{order}")).status_code == 404
        assert (await other.get(f"/api/v1/payment-orders/{order}/qr")).status_code == 404
        assert (await client.get(f"/api/v1/payment-orders/{order}/qr")).status_code == 202
        await asyncio.gather(
            worker_tick(apps["payment"], order_id=UUID(order)),
            worker_tick(apps["payment"], order_id=UUID(order)),
        )
        view = await read(client, order)
        assert (
            view["state"] == "awaiting_payment"
            and view["qr_status"] == "ready"
            and not view["paid_confirmed"]
        )
        assert school.payment_posts == {"D01": 1, "E02": 1, "E03": 1}
        image = await client.get(f"/api/v1/payment-orders/{order}/qr")
        assert image.status_code == 200 and image.content == school.png
        assert (
            image.headers["content-type"] == "image/png"
            and image.headers["cache-control"] == "no-store"
        )
        before = dict(school.payment_posts)
        refresh_path = f"/api/v1/payment-orders/{order}/qr-refresh"
        keys = [str(new_id()), str(new_id())]
        responses = await asyncio.gather(
            *(client.post(refresh_path, headers={"Idempotency-Key": key}) for key in keys)
        )
        operations = {value.json()["data"]["operation_id"] for value in responses}
        assert len(operations) == 1 and all(value.status_code == 202 for value in responses)
        operation = next(iter(operations))
        await worker_tick(apps["payment"], order_id=UUID(order))
        assert school.payment_posts == before and school.images == 2
        assert (await client.get(f"/api/v1/operations/{operation}")).json()["data"][
            "state"
        ] == "succeeded"
        assert (await other.get(f"/api/v1/operations/{operation}")).status_code == 404
        for key in keys:
            assert (await client.post(refresh_path, headers={"Idempotency-Key": key})).json()[
                "data"
            ]["operation_id"] == operation
        async with apps["payment"].state.database.connect() as conn:
            row = await first(
                conn,
                "SELECT COUNT(*) AS n FROM payment_orders WHERE owner_user_id=:owner",
                owner=UUID(user["id"]).bytes,
            )
            assert row["n"] == 1
        apps["payment"].state.side_effect_policy = SideEffectPolicy()
        assert (await create(client, binding, key=key)).status_code == 403
        assert (
            await create(client, binding, key=results[0].request.headers["idempotency-key"])
        ).status_code == 202
        apps["payment"].state.side_effect_policy = apps["school_adapter"].state.side_effect_policy
        print("金额/五并发原键/换键阻断/两用户对象隔离/两并发QR合并/图片no-store：通过")
        return order, client, binding
    finally:
        await other.aclose()


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise SystemExit("仅允许一次性验收环境")
    apps, _ = await fixture_apps()
    school = PaymentSchool()
    adapter = apps["school_adapter"].state
    adapter.school_protocol.transport.transport = httpx.MockTransport(school.handler)
    adapter.payment_transport = PaymentTransport(
        adapter.school_store, transport=httpx.MockTransport(school.handler), resolve=False
    )
    policy = SideEffectPolicy(
        payment_order_writes=True, payment_form_writes=True, payment_acceptance_passed=True
    )
    for app in apps.values():
        app.state.side_effect_policy = policy
    client = None
    try:
        order, client, binding = await basic(apps, school)
        from scripts.t6_faults import faults, status_checks

        await status_checks(apps, school, client, order, binding)
        await faults(apps, school)
    finally:
        if client:
            await client.aclose()
        # 隔离夹具保留未知订单证据，只停止此轮合成任务，防止普通进程访问假账号。
        async with apps["payment"].state.database.begin() as conn:
            for owner in getattr(apps["payment"].state, "test_owners", []):
                await execute(
                    conn,
                    "UPDATE payment_operations SET state='cancelled',lease_owner=NULL,"
                    "lease_until=NULL WHERE owner_user_id=:owner "
                    "AND state IN ('accepted','running','reconciling','unknown')",
                    owner=owner.bytes,
                )
                await execute(
                    conn,
                    "UPDATE payment_orders SET next_check_at=NULL WHERE owner_user_id=:owner",
                    owner=owner.bytes,
                )
        for app in apps.values():
            await app.state.service_client.close()
            if app.state.database:
                await app.state.database.dispose()
        await adapter.redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
