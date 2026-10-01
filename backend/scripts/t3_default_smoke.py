"""实际 MySQL 上验证 Room 默认 Saga；服务调用经签名 ASGI，无真实学校写入。"""

import asyncio
import os
from pathlib import Path
from uuid import UUID

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.room.control_jobs import claim, update
from services.room.default_saga import DefaultSaga
from services.room.defaults import accept_default, commit_preference, initialize_default
from services.room.mirror import mirror_bindings
from services.room.repository import RoomRepository


class LoseResponse:
    def __init__(self, client, path):
        self.client, self.path, self.lost = client, path, False

    async def call(self, service, path, *args, **kwargs):
        value = await self.client.call(service, path, *args, **kwargs)
        if path == self.path and not self.lost:
            self.lost = True
            raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "合成响应丢失", True)
        return value


async def expire(engine, row):
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE room_operations SET lease_until=UTC_TIMESTAMP(6),"
            "next_reconcile_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=row["id"],
        )


async def seed(engine, owner):
    records = [
        {
            "room_id": f"synthetic-default-{owner}-{number}",
            "building": "合成楼",
            "number": number,
            "balance": "25.50",
        }
        for number in ["002", "001", "003"]
    ]
    async with engine.begin() as conn:
        await mirror_bindings(conn, owner.bytes, records)
        operation = await initialize_default(conn, owner, new_id())
        rows = (
            (
                await execute(
                    conn,
                    "SELECT b.id,r.room_no FROM room_bindings b JOIN rooms r "
                    "ON b.room_id=r.id WHERE b.owner_user_id=:owner ORDER BY r.room_no",
                    owner=owner.bytes,
                )
            )
            .mappings()
            .all()
        )
    return operation, [UUID(bytes=row["id"]) for row in rows]


async def own_claim(engine, operation):
    # T2 夹具可能留有默认初始化；先安全完成这些只涉及控制的任务。
    row = await claim(engine)
    assert row and UUID(bytes=row["id"]) == operation
    return row


async def drain(app):
    from services.room.worker import control_tick

    while await control_tick(app):
        pass


async def verify_recovery(apps):
    room, monitoring = apps["room"], apps["monitoring"]
    engine, client = room.state.database, room.state.service_client
    await drain(room)
    owner = new_id()
    operation, targets = await seed(engine, owner)
    principal = Principal("room", owner, 1, new_id())
    row = await own_claim(engine, operation)
    try:
        await DefaultSaga(engine, LoseResponse(client, "/monitor/prepare-retarget")).advance(
            row, principal
        )
    except ApiError:
        pass
    async with engine.connect() as conn:
        preference = await first(
            conn, "SELECT * FROM room_preferences WHERE owner_user_id=:id", id=owner.bytes
        )
        assert preference["default_binding_id"] is None and preference["state"] == "switching"
    await expire(engine, row)
    row = await own_claim(engine, operation)
    await DefaultSaga(engine, client).advance(row, principal)
    result = await RoomRepository(engine).operation(owner, operation)
    assert result["state"] == "succeeded" and result["result_binding_id"] == str(targets[0])
    config = MonitorConfiguration(monitoring.state.database, monitoring.state.email_crypto)
    view = await config.get(owner)
    assert view.binding_id == targets[0] and view.state == "disabled" and view.generation == 3
    print("首次稳定默认、prepare响应丢失/租约接管与幂等代次：通过")

    async with engine.begin() as conn:
        operation = await accept_default(conn, owner, targets[1], 2, new_id())
    row = await own_claim(engine, operation)
    command = {
        "owner_user_id": str(owner),
        "request_id": str(principal.request_id),
        "operation_id": str(operation),
        "target_binding_id": str(targets[1]),
        "expected_preference_version": 2,
    }
    await client.call(
        "monitoring",
        "/monitor/prepare-retarget",
        "monitor:retarget",
        principal.request_id,
        command,
        principal=principal,
    )
    await update(engine, row, step="monitor_prepared")
    assert await commit_preference(engine, row, principal.request_id) == 3
    await expire(engine, row)
    recovered = await own_claim(engine, operation)
    try:
        await commit_preference(engine, row, principal.request_id)
    except ApiError as error:
        assert error.status == 409
    else:
        raise AssertionError("迟到Worker推进了偏好")
    try:
        await DefaultSaga(engine, LoseResponse(client, "/monitor/commit-retarget")).advance(
            recovered, principal
        )
    except ApiError:
        pass
    await expire(engine, recovered)
    await DefaultSaga(engine, client).advance(await own_claim(engine, operation), principal)
    view = await config.get(owner)
    assert view.binding_id == targets[1] and view.generation == 5
    print("偏好提交后崩溃、commit响应丢失向前恢复与迟到租约拒绝：通过")

    async with engine.begin() as conn:
        operation = await accept_default(conn, owner, targets[2], 3, new_id())
    row = await own_claim(engine, operation)
    command.update(
        operation_id=str(operation),
        target_binding_id=str(targets[2]),
        expected_preference_version=3,
    )
    await client.call(
        "monitoring",
        "/monitor/prepare-retarget",
        "monitor:retarget",
        principal.request_id,
        command,
        principal=principal,
    )
    view = await config.get(owner)
    await config.patch(owner, MonitorPatch(expected_version=view.version, enabled=False), new_id())
    async with engine.begin() as conn:
        await execute(
            conn, "UPDATE room_bindings SET status='rechecking' WHERE id=:id", id=targets[2].bytes
        )
    await DefaultSaga(engine, client).advance(row, principal)
    result = await RoomRepository(engine).operation(owner, operation)
    view = await config.get(owner)
    assert result["state"] == "failed" and result["default_status"] == "failed"
    assert view.binding_id == targets[1] and not view.config.enabled and view.state == "disabled"
    print("目标失效明确补偿、关闭意图与原目标保留：通过")


async def verify_browser(apps):
    engine = apps["room"].state.database
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, f"synthetic-default-api-{new_id()}"))
        owner = UUID(user["id"])
        operation, targets = await seed(engine, owner)
        await drain(apps["room"])
        monitoring = apps["monitoring"].state
        config = MonitorConfiguration(monitoring.database, monitoring.email_crypto)
        view = await config.get(owner)
        await config.patch(
            owner,
            MonitorPatch(
                expected_version=view.version, enabled=True, email="synthetic@example.invalid"
            ),
            new_id(),
        )
        assert (
            await client.put(
                "/api/v1/room-preferences/default", json={"binding_id": str(targets[1])}
            )
        ).status_code == 428
        assert (
            await client.put(
                "/api/v1/room-preferences/default",
                json={"binding_id": str(new_id()), "expected_version": 2},
            )
        ).status_code == 404
        results = await asyncio.gather(
            *(
                client.put(
                    "/api/v1/room-preferences/default",
                    json={"binding_id": str(target), "expected_version": 2},
                )
                for target in targets[1:]
            )
        )
        assert sorted(response.status_code for response in results) == [202, 409]
        accepted = next(
            response.json()["data"] for response in results if response.status_code == 202
        )
        status = (await client.get(f"/api/v1/operations/{accepted['operation_id']}")).json()["data"]
        assert status["state"] == "accepted" and status["default_status"] == "switching"
        operation = UUID(accepted["operation_id"])
        row = await own_claim(engine, operation)
        principal = Principal("room", owner, 1, new_id())
        await apps["room"].state.service_client.call(
            "monitoring",
            "/monitor/prepare-retarget",
            "monitor:retarget",
            principal.request_id,
            {
                "owner_user_id": str(owner),
                "request_id": str(principal.request_id),
                "operation_id": str(operation),
                "target_binding_id": status["target_binding_id"],
                "expected_preference_version": 2,
            },
            principal=principal,
        )
        view = await config.get(owner)
        await config.patch(
            owner, MonitorPatch(expected_version=view.version, enabled=False), new_id()
        )
        await DefaultSaga(engine, apps["room"].state.service_client).advance(row, principal)
        view = await config.get(owner)
        assert not view.config.enabled and view.state == "disabled"
        listing = (await client.get("/api/v1/room-bindings")).json()["data"]
        noop = await client.put(
            "/api/v1/room-preferences/default",
            json={"binding_id": listing["default_binding_id"], "expected_version": 3},
        )
        assert noop.status_code == 200 and listing["default_switch_operation_id"] is None
        assert (
            await client.put(
                "/api/v1/room-preferences/default",
                json={"binding_id": str(targets[0]), "expected_version": 2},
            )
        ).status_code == 409
    print("默认API 428/404/409、并发受理、终态查询与无变化200：通过")


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用显式一次性测试环境")
    apps, _ = await fixture_apps()
    try:
        await verify_recovery(apps)
        await verify_browser(apps)
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()
    print("T3 默认 Saga 实际 MySQL 验证通过；未执行学校绑定写入")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T3 默认验收失败（{type(error).__name__}）") from None
