"""绑定各阶段故障与终态边界，复用显式一次性环境。"""

import asyncio
from uuid import UUID

from scripts.t2_smoke import browser, login, prepare
from scripts.t3_binding_smoke import due, finish, select, status, submit
from services.common.config_contract import SideEffectPolicy
from services.common.ids import new_id
from services.common.internal_dto import DispatchBinding
from services.common.sql import execute, first
from services.room.worker import control_tick
from services.school_adapter.application.binding_candidates import candidate as cached_candidate
from services.school_adapter.infrastructure.binding_ledger import BindingLedger


async def verify_faults(apps, school):
    room, adapter = apps["room"], apps["school_adapter"]
    before = school.binding_posts
    async with browser(apps["gateway"]) as client:
        name = f"synthetic-binding-faults-{new_id()}"
        user = await login(client, await prepare(client, name))
        owner = UUID(user["id"])
        school.bindings[name] = [
            {**school.rooms["synthetic-room-404"], "bruId": "synthetic-existing"}
        ]
        chosen = await select(client, "synthetic-room-404")
        response = await submit(client, chosen)
        existing = response.json()["data"]["operation_id"]
        value = await finish(apps, client, existing)
        assert value["state"] == "succeeded" and school.binding_posts == before
        print("B02已存在目标直接确认、不发送学校POST：通过")

        await asyncio.sleep(1.05)
        chosen = await select(client, "synthetic-room-406")
        response = await submit(client, chosen)
        operation = response.json()["data"]["operation_id"]
        async with room.state.database.connect() as conn:
            row = await first(
                conn, "SELECT * FROM room_operations WHERE id=:id", id=UUID(operation).bytes
            )
        command = DispatchBinding(
            owner_user_id=owner,
            request_id=new_id(),
            upstream_operation_id=UUID(bytes=row["upstream_operation_id"]),
            candidate_id=chosen,
            credential_ref=UUID(bytes=row["credential_ref"]),
            credential_version=row["credential_version"],
        )
        ledger = BindingLedger(adapter.state.database, adapter.state.school_credentials.crypto)
        prepared = await ledger.prepare(
            command, await cached_candidate(adapter.state, owner, chosen)
        )
        assert (
            prepared["state"] == "prepared"
            and "不得公开".encode() not in prepared["candidate_ciphertext"]
        )
        assert await ledger.reserve(command)
        # 模拟 dispatch 已持久提交、HTTP 尚未发出就强杀：保守保持未知，不能补发。
        assert await control_tick(room)
        assert (
            school.binding_posts == before
            and (await status(client, operation))["state"] == "reconciling"
        )
        async with adapter.state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE upstream_operations SET dispatched_at=DATE_SUB(UTC_TIMESTAMP(6),"
                "INTERVAL 11 MINUTE) WHERE id=:id",
                id=command.upstream_operation_id.bytes,
            )
        await due(room, operation)
        assert await control_tick(room)
        assert (await status(client, operation))[
            "state"
        ] == "unknown" and school.binding_posts == before
        print("prepared候选密文、dispatch后HTTP前强杀不能补发、未知台账持久保留：通过")
        # 仅显式合成验收清理 Room 待执行任务，防止恢复真实 Worker 后触及学校。
        async with room.state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE room_operations SET state='cancelled',saga_step='fixture_cleanup',"
                "next_reconcile_at=NULL WHERE id=:id",
                id=UUID(operation).bytes,
            )

        await asyncio.sleep(1.05)
        chosen = await select(client, "synthetic-room-405")
        school.reject_next = True
        response = await submit(client, chosen)
        rejected = response.json()["data"]["operation_id"]
        value = await finish(apps, client, rejected)
        assert value["state"] == "failed" and value["error_code"] == "SCHOOL_BINDING_REJECTED"
        assert value["result_binding_id"] is None and school.binding_posts == before + 1
        room.state.side_effect_policy = SideEffectPolicy()
        assert (await submit(client, chosen)).status_code == 503
        room.state.side_effect_policy = SideEffectPolicy(school_binding_writes=True)
        print("学校明确业务拒绝不激活绑定、默认写开关关闭：通过")

    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, f"synthetic-default-failure-{new_id()}"))
        chosen = await select(client, "synthetic-room-402")
        response = await submit(client, chosen)
        operation = response.json()["data"]["operation_id"]
        assert await control_tick(room)
        value = await status(client, operation)
        assert value["binding_status"] == "confirmed" and value["default_status"] == "switching"
        async with room.state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE room_bindings SET status='rechecking' WHERE id=:id",
                id=UUID(value["result_binding_id"]).bytes,
            )
        value = await finish(apps, client, operation)
        assert (
            value["state"] == "succeeded"
            and value["binding_status"] == "confirmed"
            and value["default_status"] == "failed"
        )
        assert school.binding_posts == before + 2
        print("学校绑定成功而默认补偿失败分态、不能再次绑定：通过")

    async with browser(apps["gateway"]) as client:
        await login(client, await prepare(client, f"synthetic-binding-rollback-{new_id()}"))
        chosen = await select(client)
        response = await submit(client, chosen)
        operation = response.json()["data"]["operation_id"]
        from services.room import bindings

        original = bindings.append_event

        async def fail_outbox(*args, **kwargs):
            raise RuntimeError("synthetic outbox failure")

        bindings.append_event = fail_outbox
        try:
            try:
                await control_tick(room)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Outbox失败仍提交了本地绑定")
        finally:
            bindings.append_event = original
        value = await status(client, operation)
        assert value["binding_status"] == "pending" and value["result_binding_id"] is None
        value = await finish(apps, client, operation)
        assert value["state"] == "succeeded" and school.binding_posts == before + 3
        print("本地Outbox失败回滚、Adapter已确认结果恢复且POST次数不增加：通过")
