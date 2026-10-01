"""隔离MySQL/合成学校验证成功快照覆盖、学校顺序及默认/监控恢复。"""

import asyncio
import os
from uuid import UUID

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from services.common.ids import new_id
from services.common.sql import first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.room.worker import control_tick, sync_tick


async def settle(client, room, operation):
    for _ in range(100):
        data = (await client.get("/api/v1/room-bindings")).json()["data"]
        result = (await client.get(f"/api/v1/operations/{operation}")).json()["data"]
        if result["state"] in {"succeeded", "failed"} and not data["default_switch_operation_id"]:
            return data, result
        await sync_tick(room)
        await control_tick(room)
    raise AssertionError("同步/默认未在有界预算内终结")


async def sync(client, room):
    response = await client.post("/api/v1/room-bindings/sync", headers={
        "Idempotency-Key": str(new_id()),
    })
    assert response.status_code == 202
    return await settle(client, room, response.json()["data"]["operation_id"])


def target(data, number):
    return next(row["id"] for row in data["items"] if row["number"] == number)


async def verify_failure_empty_and_race(client, room, config, owner, school, data):
    school.fail_rooms = True
    failed, operation = await sync(client, room)
    assert operation["state"] == "failed" and failed["sync_status"] == "stale"
    assert failed["default_binding_id"] == data["default_binding_id"]
    assert failed["total"] == 2
    school.fail_rooms = False
    school.room_numbers = []
    empty, _ = await sync(client, room)
    assert empty["sync_status"] == "empty" and empty["items"] == []
    assert empty["default_binding_id"] is None
    assert (await config.get(owner)).binding_id is None
    print("失败不覆盖；成功空列表清空绑定/默认/监控目标：通过")

    school.room_numbers = ["004", "002"]
    data, _ = await sync(client, room)
    assert data["default_binding_id"] == target(data, "004")
    assert (await config.get(owner)).config.enabled
    chosen = await client.put("/api/v1/room-preferences/default", json={
        "binding_id": target(data, "002"), "expected_version": data["preference_version"],
    })
    assert chosen.status_code == 202
    school.room_numbers = ["005"]
    data, _ = await sync(client, room)
    assert data["total"] == 1 and data["default_binding_id"] == target(data, "005")
    assert str((await config.get(owner)).binding_id) == data["default_binding_id"]
    print("空列表后重新选第一项；在途默认失效补偿后按最新快照恢复：通过")


async def verify(apps, school):
    room, monitoring = apps["room"], apps["monitoring"].state
    owner = None
    config = MonitorConfiguration(monitoring.database, monitoring.email_crypto)
    try:
        async with browser(apps["gateway"]) as client:
            school.room_numbers = ["002", "001"]
            user = await login(client, await prepare(client, f"synthetic-sync-{new_id()}"))
            owner = UUID(user["id"])
            data, result = await sync(client, room)
            assert result["state"] == "succeeded" and data["sync_status"] == "ready"
            assert data["default_binding_id"] == target(data, "002")
            view = await config.get(owner)
            await config.patch(
                owner, MonitorPatch(expected_version=view.version, enabled=True,
                                    email="fixture@example.invalid"), new_id()
            )

            chosen = await client.put("/api/v1/room-preferences/default", json={
                "binding_id": target(data, "001"), "expected_version": data["preference_version"],
            })
            assert chosen.status_code == 202
            await control_tick(room)
            data, _ = await sync(client, room)
            before = data["preference_version"]
            assert data["default_binding_id"] == target(data, "001")
            assert (await sync(client, room))[0]["preference_version"] == before
            print("学校第一项不同于排序；仍在列表的本人默认保持不变：通过")

            school.room_numbers = ["003", "002"]
            data, _ = await sync(client, room)
            assert data["total"] == 2 and {row["number"] for row in data["items"]} == {"003", "002"}
            assert all(row["status"] == "active" for row in data["items"])
            assert data["default_binding_id"] == target(data, "003")
            view = await config.get(owner)
            assert str(view.binding_id) == data["default_binding_id"] and view.config.enabled
            async with room.state.database.connect() as conn:
                historical = await first(conn, "SELECT COUNT(*) AS n FROM room_bindings "
                    "WHERE owner_user_id=:owner AND status='inactive'", owner=owner.bytes)
            assert historical["n"] == 1
            print("成功快照覆盖旧列表、缺席默认回退学校第一项、监控跟随且保留历史：通过")

            await verify_failure_empty_and_race(client, room, config, owner, school, data)
    finally:
        if owner:
            view = await config.get(owner)
            await config.patch(
                owner, MonitorPatch(expected_version=view.version, enabled=False), new_id()
            )


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅允许隔离测试项目")
    apps, school = await fixture_apps()
    try:
        await verify(apps, school)
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
