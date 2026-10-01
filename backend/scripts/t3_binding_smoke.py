"""实际 MySQL 与合成学校验证绑定一次写入、回查、权限和默认子操作。"""

import asyncio
import os
from pathlib import Path
from uuid import UUID

import httpx

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from scripts.t3_binding_fixtures import BindingSchool
from services.common.config_contract import SideEffectPolicy
from services.common.ids import new_id
from services.common.sql import execute
from services.room.worker import control_tick


async def due(app, operation):
    async with app.state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE room_operations SET next_reconcile_at=UTC_TIMESTAMP(6),"
            "lease_until=NULL WHERE id=:id",
            id=UUID(operation).bytes,
        )


async def status(client, operation):
    response = await client.get(f"/api/v1/operations/{operation}")
    assert response.status_code == 200
    return response.json()["data"]


async def select(client, room="synthetic-room-402"):
    value = await client.get("/api/v1/room-candidates", params={"room_id": room})
    assert value.status_code == 200
    return value.json()["data"]["items"][0]["candidate_id"]


async def submit(client, candidate, key=None):
    return await client.post(
        "/api/v1/room-bindings",
        json={"candidate_id": candidate},
        headers={"Idempotency-Key": key or str(new_id())},
    )


async def finish(apps, client, operation):
    for _ in range(12):
        value = await status(client, operation)
        if value["state"] in {"succeeded", "failed"}:
            return value
        await due(apps["room"], operation)
        assert await control_tick(apps["room"])
    raise AssertionError("合成操作未能终结")


async def verify(apps, school):
    room = apps["room"]
    # 前阶段的默认控制任务不访问学校，先完成以隔离后续领取。
    while await control_tick(room):
        pass
    async with browser(apps["gateway"]) as client, browser(apps["gateway"]) as other:
        name = f"synthetic-binding-{new_id()}"
        user = await login(client, await prepare(client, name))
        await login(other, await prepare(other, f"synthetic-other-{new_id()}"))
        for path, params in [
            ("buildings", {}),
            ("floors", {"building_id": "synthetic-building"}),
            ("rooms", {"building_id": "synthetic-building", "floor": "4"}),
        ]:
            response = await client.get(f"/api/v1/room-candidates/{path}", params=params)
            assert response.status_code == 200 and response.json()["data"]["items"]
            assert "userName" not in response.text and "userId" not in response.text
        assert (await client.get("/api/v1/room-candidates/floors")).status_code == 422
        print("三级筛选、楼层值解析、必填父项、脱敏字段：通过")

        candidate = await select(client)
        key = str(new_id())
        forbidden = await submit(other, candidate)
        assert forbidden.status_code == 404
        assert (await submit(client, "expired-missing-candidate")).status_code == 400
        results = await asyncio.gather(
            submit(client, candidate, key), submit(client, candidate, key)
        )
        assert all(response.status_code == 202 for response in results)
        operation = results[0].json()["data"]["operation_id"]
        assert results[1].json()["data"]["operation_id"] == operation
        assert (await submit(client, "changed-candidate", key)).status_code == 409
        conflict = await submit(client, candidate)
        assert (
            conflict.status_code == 409
            and conflict.json()["error"]["existing_operation_id"] == operation
        )
        assert (await other.get(f"/api/v1/operations/{operation}")).status_code == 404
        print("候选归属/过期、并发同键、内容冲突与换键目标屏障：通过")

        school.lose_next = True
        assert await control_tick(room)
        value = await status(client, operation)
        assert value["state"] == "reconciling" and value["binding_status"] == "pending"
        assert school.binding_posts == 1
        # 只回查阶段不依赖候选缓存；删除模拟 Redis 丢失或重启。
        await apps["school_adapter"].state.school_store.call(
            "delete", f"school_adapter:candidate:{candidate}"
        )
        assert (await submit(client, candidate, key)).json()["data"]["operation_id"] == operation
        await due(room, operation)
        assert await control_tick(room)
        value = await status(client, operation)
        assert value["binding_status"] == "confirmed" and value["default_status"] == "switching"
        assert value["state"] not in {"failed", "succeeded"}
        completed = await finish(apps, client, operation)
        assert (
            completed["binding_status"] == "confirmed"
            and completed["default_status"] == "confirmed"
        )
        listing = (await client.get("/api/v1/room-bindings")).json()["data"]
        assert (
            listing["default_binding_id"] == completed["result_binding_id"]
            and school.binding_posts == 1
        )
        assert (
            await client.get(f"/api/v1/room-bindings/{completed['result_binding_id']}")
        ).status_code == 200
        assert (
            await other.get(f"/api/v1/room-bindings/{completed['result_binding_id']}")
        ).status_code == 404
        print("学校写入后响应丢失、缓存丢失/重启只回查、学校与默认分态、首次自动默认：通过")

        await asyncio.sleep(1.05)
        candidate = await select(client, "synthetic-room-403")
        response = await submit(client, candidate)
        unknown_id = response.json()["data"]["operation_id"]
        school.hidden.add("synthetic-room-403")
        school.lose_next = True
        assert await control_tick(room)
        async with apps["school_adapter"].state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE upstream_operations SET dispatched_at=DATE_SUB(UTC_TIMESTAMP(6),"
                "INTERVAL 11 MINUTE) WHERE owner_user_id=:owner "
                "AND target_ref='synthetic-room-403'",
                owner=UUID(user["id"]).bytes,
            )
        await due(room, unknown_id)
        assert await control_tick(room)
        assert (await status(client, unknown_id))["state"] == "unknown"
        assert (await submit(client, candidate)).status_code == 409 and school.binding_posts == 2
        school.hidden.clear()
        complete = await finish(apps, client, unknown_id)
        assert complete["state"] == "succeeded" and complete["default_status"] == "unchanged"
        assert (await client.get("/api/v1/room-bindings")).json()["data"][
            "default_binding_id"
        ] == listing["default_binding_id"]
        assert school.binding_posts == 2
        async with apps["school_adapter"].state.database.connect() as conn:
            rows = (
                (
                    await execute(
                        conn,
                        "SELECT candidate_ciphertext,confirmed_record FROM upstream_operations "
                        "WHERE owner_user_id=:owner",
                        owner=UUID(user["id"]).bytes,
                    )
                )
                .mappings()
                .all()
            )
            assert all(
                row["candidate_ciphertext"] is None and "userName" not in row["confirmed_record"]
                for row in rows
            )
        print("10分钟 unknown、空列表与换键不能再写、恢复确认且已有默认保留、敏感候选清除：通过")
        return user


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用显式一次性测试环境")
    if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
        from services.common.logging import configure_logging

        configure_logging()
    apps, _ = await fixture_apps()
    school = BindingSchool()
    apps["school_adapter"].state.school_protocol.transport.transport = httpx.MockTransport(
        school.handler
    )
    for service in ["room", "school_adapter"]:
        apps[service].state.side_effect_policy = SideEffectPolicy(school_binding_writes=True)
    try:
        await verify(apps, school)
        from scripts.t3_binding_faults import verify_faults

        await verify_faults(apps, school)
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()
    print("T3 绑定实际 MySQL/合成学校验收通过；未连接真实学校")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T3 绑定验收失败（{type(error).__name__}）") from None
