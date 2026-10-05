"""MySQL 解绑：单次写、缺席复核、默认屏障和关闭竞态；合成学校。"""

import asyncio
import os
from pathlib import Path
from uuid import UUID

import httpx

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t3_binding_smoke import due, select, status, submit
from scripts.t3_binding_smoke import finish as finish_binding
from scripts.t3_removal_fixtures import RemovalSchool
from services.common.config_contract import SideEffectPolicy
from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.room.worker import control_tick


async def accept(client, binding, key=None):
    return await client.delete(
        f"/api/v1/room-bindings/{binding}", headers={"Idempotency-Key": key or str(new_id())}
    )


async def age_absence(apps, operation):
    async with apps["room"].state.database.connect() as conn:
        row = await first(
            conn,
            "SELECT upstream_operation_id FROM room_operations WHERE id=:id",
            id=UUID(operation).bytes,
        )
    async with apps["school_adapter"].state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE upstream_operations SET absence_first_at=DATE_SUB(UTC_TIMESTAMP(6),"
            "INTERVAL 3 SECOND) WHERE id=:id AND absence_first_at IS NOT NULL",
            id=row["upstream_operation_id"],
        )


async def finish_removal(apps, client, operation):
    for _ in range(12):
        value = await status(client, operation)
        if value["state"] in {"succeeded", "failed"}:
            return value
        await age_absence(apps, operation)
        await due(apps["room"], operation)
        assert await control_tick(apps["room"])
    raise AssertionError("解绑未终结")


async def bind(client, apps, target):
    candidate = await select(client, target)
    response = await submit(client, candidate)
    assert response.status_code == 202
    value = await finish_binding(apps, client, response.json()["data"]["operation_id"])
    assert value["state"] == "succeeded"
    return value["result_binding_id"]


async def verify(apps, school):
    room = apps["room"]
    while await control_tick(room):
        pass
    async with browser(apps["gateway"]) as client, browser(apps["gateway"]) as other:
        user = await login(client, await prepare(client, f"synthetic-remove-{new_id()}"))
        await login(other, await prepare(other, f"synthetic-remove-other-{new_id()}"))
        first_binding = await bind(client, apps, "synthetic-room-402")
        await asyncio.sleep(1.05)
        second_binding = await bind(client, apps, "synthetic-room-403")
        assert (await accept(other, second_binding)).status_code == 404
        key = str(new_id())
        responses = await asyncio.gather(
            accept(client, second_binding, key), accept(client, second_binding, key)
        )
        assert all(response.status_code == 202 for response in responses)
        operation = responses[0].json()["data"]["operation_id"]
        assert responses[1].json()["data"]["operation_id"] == operation
        assert (await accept(client, first_binding, key)).status_code == 409
        assert (await accept(client, second_binding)).status_code == 409
        assert (await other.get(f"/api/v1/operations/{operation}")).status_code == 404
        print("解绑归属/同键/换键/原目标保护与持久受理：通过")
        school.lose_remove_next = True
        assert await control_tick(room)
        assert school.remove_posts == 1
        value = await status(client, operation)
        assert value["state"] == "reconciling" and value["binding_status"] == "pending"
        # 响应丢失后第一次真实缺席只是观察，不能清本域绑定。
        await due(room, operation)
        assert await control_tick(room)
        value = await status(client, operation)
        assert value["binding_status"] == "pending"
        assert (await client.get(f"/api/v1/room-bindings/{second_binding}")).status_code == 200
        value = await finish_removal(apps, client, operation)
        assert value["state"] == "succeeded" and value["binding_status"] == "removed"
        assert value["default_status"] == "unchanged" and school.remove_posts == 1
        listing = (await client.get("/api/v1/room-bindings")).json()["data"]
        assert listing["default_binding_id"] == first_binding and listing["total"] == 1
        assert (await client.get(f"/api/v1/room-bindings/{second_binding}")).status_code == 404
        assert (await accept(client, second_binding, key)).json()["data"][
            "operation_id"
        ] == operation
        print("POST方法覆盖一次发送、响应丢失/两次30秒缺席、原默认/镜像/重复受理：通过")

        monitor = apps["monitoring"].state
        config = MonitorConfiguration(monitor.database, monitor.email_crypto)
        owner = UUID(user["id"])
        view = await config.get(owner)
        await config.patch(
            owner,
            MonitorPatch(
                expected_version=view.version, enabled=True, email="synthetic@example.invalid"
            ),
            new_id(),
        )
        response = await accept(client, first_binding)
        operation = response.json()["data"]["operation_id"]
        school.hold_remove = True
        assert await control_tick(room)
        view = await config.get(owner)
        assert view.state == "retargeting" and view.binding_id == UUID(first_binding)
        assert (
            await client.put(
                "/api/v1/room-preferences/default",
                json={"binding_id": second_binding, "expected_version": 2},
            )
        ).status_code == 409
        await config.patch(
            owner, MonitorPatch(expected_version=view.version, enabled=False), new_id()
        )
        # 一次空列表之后重新出现，缺席证据必须重置。
        school.empty_once = True
        await due(room, operation)
        assert await control_tick(room)
        await age_absence(apps, operation)
        await due(room, operation)
        assert await control_tick(room)
        assert (await status(client, operation))["binding_status"] == "pending"
        async with apps["school_adapter"].state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE upstream_operations SET dispatched_at=DATE_SUB(UTC_TIMESTAMP(6),"
                "INTERVAL 11 MINUTE) WHERE owner_user_id=:owner "
                "AND target_ref='synthetic-room-402'",
                owner=owner.bytes,
            )
        await due(room, operation)
        assert await control_tick(room)
        assert (await status(client, operation))["state"] == "unknown" and school.remove_posts == 2
        # 学校最终完成同一次删除，未知操作只能回查。
        for key_name in list(school.bindings):
            school.bindings[key_name] = [
                record
                for record in school.bindings[key_name]
                if record["roomId"] != "synthetic-room-402"
            ]
        school.hold_remove = False
        value = await finish_removal(apps, client, operation)
        assert value["state"] == "succeeded" and value["default_status"] == "confirmed"
        view = await config.get(owner)
        assert view.binding_id is None and view.state == "disabled" and not view.config.enabled
        listing = (await client.get("/api/v1/room-bindings")).json()["data"]
        assert (
            listing["default_binding_id"] is None
            and listing["preference_state"] == "blocked"
            and listing["total"] == 0
        )
        async with room.state.database.connect() as conn:
            kept = await first(
                conn,
                "SELECT COUNT(*) AS n FROM room_balance_cache c JOIN room_bindings b "
                "ON b.id=c.binding_id "
                "WHERE b.owner_user_id=:owner AND b.status='inactive'",
                owner=owner.bytes,
            )
            assert kept["n"] == 2
        print("默认先屏障、瞬态空列表/unknown不重复删除、关闭意图、清默认且历史缓存保留：通过")


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于显式一次性环境")
    apps, _ = await fixture_apps()
    school = RemovalSchool()
    apps["school_adapter"].state.school_protocol.transport.transport = httpx.MockTransport(
        school.handler
    )
    for service in ["room", "school_adapter"]:
        apps[service].state.side_effect_policy = SideEffectPolicy(school_binding_writes=True)
    try:
        await verify(apps, school)
        from scripts.t3_removal_faults import verify_faults

        await verify_faults(apps, school)
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()
    print("T3 解绑 MySQL/合成学校验收通过；未连接真实学校")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T3 解绑验收失败（{type(error).__name__}）") from None
