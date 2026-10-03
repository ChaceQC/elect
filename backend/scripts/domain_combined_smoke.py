"""七域实际后台共同运行；学校/支付由MockTransport处理，SMTP不外发。"""

import asyncio
import os
from uuid import UUID

import httpx

from scripts.monitoring_combined_smoke import run_state, sample_count, until
from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t4_monitor_smoke import enable, run_request
from scripts.t4_query_smoke import QuerySchool
from scripts.t5_fixtures import close_apps, make_job, notification_app
from scripts.t6_fixtures import PaymentSchool
from scripts.t6_smoke import create, due, read
from services.common.app import create_app
from services.common.background import start_background
from services.common.config_contract import SideEffectPolicy
from services.common.database import create_database, migration_head
from services.common.ids import new_id
from services.common.runtime import Runtime, read_secret
from services.common.service_client import ServiceClient
from services.common.sql import execute, first
from services.school_adapter.infrastructure.payment_transport import PaymentTransport


async def order_unknown(client, order):
    return (await read(client, order))["state"] == "submit_unknown"


async def job_unknown(app, job):
    async with app.state.database.connect() as conn:
        row = await first(conn, "SELECT state FROM notification_jobs WHERE id=:id", id=job)
    return row["state"] == "delivery_unknown"


async def bound(client):
    value = (await client.get("/api/v1/room-bindings")).json()["data"]
    return bool(value["items"]) and value["sync_status"] == "ready"


async def default_ready(client):
    value = (await client.get("/api/v1/room-bindings")).json()["data"]
    return value["default_binding_id"] is not None and value["default_switch_operation_id"] is None


async def setup():
    apps, _ = await fixture_apps()
    await notification_app(apps)
    runtime = Runtime.model_validate_json(read_secret("/run/secrets/audit_runtime.json"))
    app = create_app("audit", business=True)
    app.state.runtime, app.state.public_origin = runtime, "https://elect.test.local"
    app.state.database = create_database(runtime.db_url.get_secret_value())
    app.state.service_client = ServiceClient(
        runtime, transport=apps["monitoring"].state.service_client.client._transport,
    )
    apps["audit"] = app
    school = PaymentSchool()
    query = QuerySchool(school)
    query.first_balance, query.missing_second = "19.99", True
    adapter = apps["school_adapter"].state
    adapter.school_protocol.transport.transport = httpx.MockTransport(query.handler)
    adapter.payment_transport = PaymentTransport(
        adapter.school_store, transport=httpx.MockTransport(school.handler), resolve=False,
    )
    policy = SideEffectPolicy(
        payment_order_writes=True, payment_form_writes=True, payment_acceptance_passed=True,
    )
    for name, app in apps.items():
        app.state.migration_head = migration_head(name) if app.state.database else None
        app.state.side_effect_policy = policy
    return apps, school


async def verify(apps, school):
    for name, app in apps.items():
        await start_background(app, name)
    monitor, payment, notification = apps["monitoring"], apps["payment"], apps["notification"]
    async with browser(apps["gateway"]) as client:
        name = "synthetic-domains-" + str(new_id())
        school.bindings[name] = [
            {**school.rooms["synthetic-room-402"], "bruId": "synthetic-relation"},
        ]
        user = await login(client, await prepare(client, name))
        owner = UUID(user["id"])
        payment.state.test_owners = [owner]
        await client.post("/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())})
        await until(lambda: bound(client))
        await until(lambda: default_ready(client))
        binding = (await client.get("/api/v1/room-bindings")).json()["data"]["items"][0]["id"]
        print("七域角色共同运行，Room自动同步/默认Saga通过，未手工执行业务tick")
        await enable(client)
        run = await run_request(client)
        await until(lambda: run_state(monitor.state.database, run, "succeeded"))
        assert await sample_count(monitor.state.database, run) == 1
        async with monitor.state.database.connect() as conn:
            sample = await first(
                conn, "SELECT id FROM monitor_samples WHERE run_id=:id", id=run.bytes,
            )
        job, _ = await make_job(apps, UUID(bytes=sample["id"]))
        # 合成DATA后崩溃，合并恢复器必须保留unknown，API角色组合不得发送SMTP。
        async with notification.state.database.begin() as conn:
            await execute(conn, "UPDATE notification_jobs SET state='sending',"
                          "body_started_at=UTC_TIMESTAMP(6),lease_until=UTC_TIMESTAMP(6) "
                          "WHERE id=:id",
                          id=job["id"])
        await until(lambda: job_unknown(notification, job["id"]))
        assert notification.state.smtp is None
        print("合并Notification恢复DATA后unknown、发送Worker独立：通过")
        school.lose = "D01"
        key = str(new_id())
        responses = await asyncio.gather(*(create(client, binding, key=key) for _ in range(3)))
        assert all(response.status_code == 202 for response in responses)
        order = responses[0].json()["data"]["order_id"]
        assert {response.json()["data"]["order_id"] for response in responses} == {order}
        await until(lambda: order_unknown(client, order))
        await due(payment, order)
        previous = payment.state.background.heartbeats["worker"].document["processed"]

        async def advanced():
            return payment.state.background.heartbeats["worker"].document["processed"] > previous

        await until(advanced)
        assert school.payment_posts["D01"] == 1 and await order_unknown(client, order)
        print("合并Payment自动执行、响应丢失unknown回查、重复受理仍仅一次D01：通过")
        async with apps["school_adapter"].state.database.begin() as conn:
            await execute(conn, "UPDATE credential_staging SET expires_at=UTC_TIMESTAMP(6) "
                          "WHERE encrypted_payload<>''")

        async def cleaned():
            async with apps["school_adapter"].state.database.connect() as conn:
                row = await first(conn, "SELECT COUNT(*) AS n FROM credential_staging "
                                  "WHERE expires_at<=UTC_TIMESTAMP(6) AND encrypted_payload<>''")
            return row["n"] == 0

        await until(cleaned)
        for app in apps.values():
            if app.state.background:
                await until(lambda app=app: available(app))
        print("七域独立角色心跳/共享AMQP、Adapter过期暂存清理：通过")


async def available(app):
    return app.state.background.available()


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅允许一次性验收环境")
    os.environ["ELECT_PROCESS_MODE"], os.environ["ELECT_BACKGROUND_ENABLED"] = "combined", "true"
    apps, school = await setup()
    try:
        await verify(apps, school)
    finally:
        for app in apps.values():
            supervisor = getattr(app.state, "background", None)
            if supervisor:
                supervisor.shutdown_timeout = 0
                await supervisor.close()
        async with apps["payment"].state.database.begin() as conn:
            for owner in getattr(apps["payment"].state, "test_owners", []):
                await execute(conn, "UPDATE payment_operations SET "
                              "state='cancelled',lease_owner=NULL,"
                              "lease_until=NULL WHERE owner_user_id=:owner", owner=owner.bytes)
                await execute(conn, "UPDATE payment_orders SET next_check_at=NULL "
                              "WHERE owner_user_id=:owner", owner=owner.bytes)
        await close_apps(apps)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{frame.name}:{frame.lineno}")
        raise SystemExit(f"七域合并验收失败（{type(error).__name__}）") from None
