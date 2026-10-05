"""响应丢失/持久阶段恢复/未验收状态与余额来源检查。"""

from uuid import UUID

from scripts.t6_smoke import account, create, due, read
from services.common.ids import new_id
from services.common.sql import execute
from services.payment.reconciliation import check_tick
from services.payment.worker import worker_tick
from services.room.query_worker import query_tick


async def status_checks(apps, school, client, order, binding):
    school.status = "PAID"
    await due(apps["payment"], order)
    await check_tick(apps["payment"], order_id=UUID(order))
    assert (await read(client, order))["state"] == "status_unknown"
    assert (await create(client, binding)).status_code == 409
    # 使用已验收D04的字符串2，合成订单标识必须与原票据精确匹配。
    original = school.status
    school.status = "2"
    try:
        await due(apps["payment"], order)
        await check_tick(apps["payment"], order_id=UUID(order))
        view = await read(client, order)
        assert view["paid_confirmed"] and view["balance_refresh_state"] == "pending"
        await query_tick(apps["room"])
        await due(apps["payment"], order)
        await check_tick(apps["payment"], order_id=UUID(order))
        view = await read(client, order)
        assert view["balance_refresh_state"] == "succeeded"
        balance = (await client.get(f"/api/v1/room-bindings/{binding}/balance")).json()["data"]
        assert balance["amount"] == "25.50"  # 不以25.50 + 20.00伪造到账。
        assert (await client.get(f"/api/v1/payment-orders/{order}/qr")).status_code == 409
    finally:
        school.status = original
    print("未经验证的PAID保持未知；D04精确映射终结并持久刷新学校余额，不做加法：通过")


async def faults(apps, school):
    for step in ("D01", "E02", "E03", "E04"):
        client, _, binding = await account(apps, school)
        try:
            before = dict(school.payment_posts)
            school.lose = step if step != "E04" else None
            school.fail_image = step == "E04"
            order = (await create(client, binding)).json()["data"]["order_id"]
            await worker_tick(apps["payment"], order_id=UUID(order))
            view = await read(client, order)
            if step == "D01":
                assert view["state"] == "submit_unknown"
                await due(apps["payment"], order)
                await check_tick(apps["payment"], order_id=UUID(order))
                assert (await read(client, order))["state"] == "submit_unknown"
                assert (await create(client, binding)).status_code == 409
                await due(apps["payment"], order)
                await worker_tick(apps["payment"], order_id=UUID(order))
                assert school.payment_posts["D01"] == before["D01"] + 1
            elif step in {"E02", "E03"}:
                assert view["qr_status"] == "unknown"
                response = await client.post(
                    f"/api/v1/payment-orders/{order}/qr-refresh",
                    headers={"Idempotency-Key": str(new_id())},
                )
                assert response.status_code == 202
                await due(apps["payment"], order)
                await worker_tick(apps["payment"], order_id=UUID(order))
                assert (await read(client, order))["qr_status"] == "unknown"
                assert school.payment_posts[step] == before[step] + 1
            else:
                assert view["qr_status"] == "failed"
                failed_posts = dict(school.payment_posts)
                school.fail_image = False
                await client.post(
                    f"/api/v1/payment-orders/{order}/qr-refresh",
                    headers={"Idempotency-Key": str(new_id())},
                )
                await worker_tick(apps["payment"], order_id=UUID(order))
                assert (await read(client, order))["qr_status"] == "ready"
                assert school.payment_posts == failed_posts
            assert school.payment_posts["D01"] == before["D01"] + 1
        finally:
            await client.aclose()
    await crash_after_form(apps, school)
    print("D01/E02/E03响应丢失不重复；E04失败只重取同订单图片；持久表单阶段恢复：通过")


async def crash_after_form(apps, school):
    from services.common.http import ApiError
    from services.payment import jobs
    from services.payment.worker import advance
    from services.school_adapter.infrastructure.payment_sessions import PaymentSessions

    client, _, binding = await account(apps, school)
    original = PaymentSessions.save

    async def interrupted(self, command, lease, step, *args, **kwargs):
        if step == "E02":
            raise RuntimeError("合成进程在表单响应后、持久化前退出")
        return await original(self, command, lease, step, *args, **kwargs)

    before = dict(school.payment_posts)
    try:
        order = (await create(client, binding)).json()["data"]["order_id"]
        PaymentSessions.save = interrupted
        execution = await jobs.claim(apps["payment"].state.database, UUID(order))
        try:
            await advance(apps["payment"], execution)
            raise AssertionError("故障注入未触发")
        except ApiError:
            pass
        PaymentSessions.save = original
        async with apps["payment"].state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE payment_operations SET "
                "lease_until=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) "
                "WHERE order_id=:id AND state='running'",
                id=UUID(order).bytes,
            )
        assert await jobs.recover(apps["payment"].state.database)
        await due(apps["payment"], order)
        await worker_tick(apps["payment"], order_id=UUID(order))
        assert not await jobs.update(
            apps["payment"].state.database,
            execution,
            qr_status="ready",
            operation_state="succeeded",
        )
        assert (await read(client, order))["qr_status"] == "unknown"
        assert (
            school.payment_posts["D01"] == before["D01"] + 1
            and school.payment_posts["E02"] == before["E02"] + 1
        )
    finally:
        PaymentSessions.save = original
        await client.aclose()
