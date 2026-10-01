"""解绑补偿、各持久阶段故障和迟到租约；不触及真实学校。"""

from uuid import UUID

from scripts.t2_smoke import browser, login, prepare
from scripts.t3_default_smoke import LoseResponse
from scripts.t3_removal_smoke import accept, age_absence, bind, due, finish_removal, status
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import DispatchRemoval
from services.common.security import Principal
from services.common.sql import first
from services.monitoring.configuration import MonitorConfiguration
from services.room.control_jobs import claim
from services.room.removal_saga import RemovalSaga
from services.room.worker import control_tick
from services.school_adapter.application.removal_writes import RemovalWrites


async def row_for(apps, operation):
    async with apps["room"].state.database.connect() as conn:
        return await first(
            conn,
            "SELECT o.*,r.school_room_id FROM room_operations o JOIN rooms r "
            "ON r.id=o.target_room_id WHERE o.id=:id",
            id=UUID(operation).bytes,
        )


async def verify_faults(apps, school):
    room = apps["room"]
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, f"synthetic-remove-faults-{new_id()}"))
        owner = UUID(user["id"])
        target = await bind(client, apps, "synthetic-room-404")
        before = school.remove_posts
        school.reject_remove_next = True
        response = await accept(client, target)
        operation = response.json()["data"]["operation_id"]
        value = await finish_removal(apps, client, operation)
        assert value["state"] == "failed" and value["error_code"] == "SCHOOL_BINDING_REJECTED"
        listing = (await client.get("/api/v1/room-bindings")).json()["data"]
        assert (
            listing["default_binding_id"] == target
            and listing["binding_removal_operation_id"] is None
        )
        config = MonitorConfiguration(
            apps["monitoring"].state.database, apps["monitoring"].state.email_crypto
        )
        view = await config.get(owner)
        assert view.binding_id == UUID(target) and view.state == "disabled"
        print("默认解绑明确学校拒绝、原默认/目标补偿及新代次：通过")

        response = await accept(client, target)
        operation = response.json()["data"]["operation_id"]
        leased = await claim(room.state.database)
        assert UUID(bytes=leased["id"]) == UUID(operation)
        row = await row_for(apps, operation)
        principal = Principal("room", owner, 1, new_id())
        saga = RemovalSaga(room.state.database, room.state.service_client)
        await saga.barrier("/monitor/prepare-retarget", leased, principal)
        command = DispatchRemoval(
            owner_user_id=owner,
            request_id=new_id(),
            upstream_operation_id=UUID(bytes=row["upstream_operation_id"]),
            room_operation_id=UUID(operation),
            room_id=row["school_room_id"],
            credential_ref=UUID(bytes=row["credential_ref"]),
            credential_version=row["credential_version"],
            lease_owner=leased["lease_owner"],
        )
        # 失去 Room 租约的旧 Worker 不能取得学校首次发送许可。
        await due(room, operation)
        try:
            await RemovalWrites(apps["school_adapter"].state).dispatch(command, principal)
        except ApiError as error:
            assert error.code == ErrorCode.OPERATION_IN_PROGRESS
        else:
            raise AssertionError("迟到租约删除了学校绑定")
        assert school.remove_posts == before + 1
        # 新 Worker 接管后发送一次，第一次缺席仍待确认。
        assert await control_tick(room)
        assert school.remove_posts == before + 2
        await age_absence(apps, operation)
        await due(room, operation)
        leased = await claim(room.state.database)
        losing = RemovalSaga(
            room.state.database, LoseResponse(room.state.service_client, "/monitor/commit-retarget")
        )
        try:
            await losing.advance(leased, principal)
        except ApiError:
            pass
        else:
            raise AssertionError("没有模拟确认响应丢失")
        value = await status(client, operation)
        assert value["binding_status"] == "removed" and value["state"] not in {
            "succeeded",
            "failed",
        }
        value = await finish_removal(apps, client, operation)
        assert value["state"] == "succeeded" and school.remove_posts == before + 2
        view = await config.get(owner)
        assert view.binding_id is None
        print("迟到租约不能首次删除、偏好提交/monitor确认响应丢失向前恢复、不重复学校写：通过")

    async with browser(apps["gateway"]) as client:
        await login(client, await prepare(client, f"synthetic-remove-outbox-{new_id()}"))
        target = await bind(client, apps, "synthetic-room-405")
        response = await accept(client, target)
        operation = response.json()["data"]["operation_id"]
        assert await control_tick(room)
        await age_absence(apps, operation)
        await due(room, operation)
        from services.room import removals

        original = removals.record_audit

        async def fail_outbox(*args, **kwargs):
            raise RuntimeError("synthetic outbox failure")

        removals.record_audit = fail_outbox
        before = school.remove_posts
        try:
            try:
                await control_tick(room)
            except RuntimeError:
                pass
            else:
                raise AssertionError("审计Outbox失败仍清理了本域默认")
        finally:
            removals.record_audit = original
        assert (await client.get(f"/api/v1/room-bindings/{target}")).status_code == 200
        value = await finish_removal(apps, client, operation)
        assert value["state"] == "succeeded" and school.remove_posts == before
        print("学校解绑已确认、本域Outbox失败原子回滚/恢复、不再次删除：通过")
