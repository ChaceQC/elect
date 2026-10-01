"""控制 API 真实内部签名链和事务并发验证，使用合成 Room 提交记录。"""

import asyncio

import httpx

from scripts.t3_control_fixtures import running, write_sample
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import RevokeBarrier
from services.common.security import Principal
from services.common.service_client import ServiceClient
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.credentials import CredentialControls
from services.monitoring.dto import MonitorPatch
from services.monitoring.fences import fenced_transaction


def connect_monitoring(apps):
    async def dispatch(request):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=apps[request.url.host]), base_url=str(request.url)
        ) as client:
            return await client.request(
                request.method, str(request.url), headers=request.headers, content=request.content
            )

    app = apps["monitoring"]
    app.state.service_client = ServiceClient(
        app.state.runtime, transport=httpx.MockTransport(dispatch)
    )


async def verify_proof_api(apps):
    owner, target, operation, request_id = new_id(), new_id(), new_id(), new_id()
    client = apps["room"].state.service_client
    principal = Principal("room", owner, 1, request_id)
    prepare = {
        "owner_user_id": str(owner),
        "request_id": str(request_id),
        "operation_id": str(operation),
        "target_binding_id": str(target),
        "expected_preference_version": 1,
    }
    await client.call(
        "monitoring",
        "/monitor/prepare-retarget",
        "monitor:retarget",
        request_id,
        prepare,
        principal=principal,
    )
    commit = {key: value for key, value in prepare.items() if key != "expected_preference_version"}
    commit["committed_preference_version"] = 2
    async with apps["room"].state.database.begin() as conn:
        await execute(
            conn,
            "INSERT INTO room_operations (id,owner_user_id,type,target_binding_id,request_digest,"
            "state,saga_step,expected_preference_version) VALUES "
            "(:id,:owner,'switch_default',:target,:digest,'running','monitor_prepared',1)",
            id=operation.bytes,
            owner=owner.bytes,
            target=target.bytes,
            digest=b"s" * 32,
        )
    try:
        await client.call(
            "monitoring",
            "/monitor/commit-retarget",
            "monitor:retarget",
            request_id,
            commit,
            principal=principal,
        )
    except ApiError as error:
        assert error.status == 409
    else:
        raise AssertionError("未经 Room 提交证明就完成切换")
    async with apps["room"].state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE room_operations SET saga_step='preference_committed',"
            "committed_preference_version=2 WHERE id=:id",
            id=operation.bytes,
        )
    try:
        await client.call(
            "monitoring",
            "/monitor/commit-retarget",
            "monitor:retarget",
            request_id,
            commit,
            principal=principal,
        )
    except ApiError as error:
        assert error.status == 409
    else:
        raise AssertionError("操作标记与实际偏好不一致仍允许提交")
    async with apps["room"].state.database.begin() as conn:
        room_id = new_id()
        await execute(
            conn,
            "INSERT INTO rooms (id,school_id,school_room_id,building_name,room_no,"
            "metadata_version) "
            "VALUES (:id,'hbue',:school,'合成楼','001',1)",
            id=room_id.bytes,
            school=f"synthetic-proof-{room_id}",
        )
        await execute(
            conn,
            "INSERT INTO room_bindings (id,owner_user_id,room_id,status) "
            "VALUES (:id,:owner,:room,'active')",
            id=target.bytes,
            owner=owner.bytes,
            room=room_id.bytes,
        )
        await execute(
            conn,
            "INSERT INTO room_preferences "
            "(owner_user_id,default_binding_id,version,switch_operation_id,state) "
            "VALUES (:owner,:binding,2,:operation,'switching')",
            owner=owner.bytes,
            binding=target.bytes,
            operation=operation.bytes,
        )
    result = await client.call(
        "monitoring",
        "/monitor/commit-retarget",
        "monitor:retarget",
        request_id,
        commit,
        principal=principal,
    )
    assert result["state"] == "committed"
    try:
        await client.call(
            "monitoring",
            "/monitor/prepare-retarget",
            "monitor:retarget",
            request_id,
            prepare,
            principal=Principal("room", new_id(), 1, request_id),
        )
    except ApiError as error:
        assert error.status == 404
    else:
        raise AssertionError("跨用户控制未被拒绝")
    print("Room→Monitoring→Room 提交证明、未提交拒绝及跨用户控制拒绝：通过")


async def verify_result_race(engine, crypto):
    owner = new_id()
    execution, _ = await running(engine, owner)
    configuration = MonitorConfiguration(engine, crypto)
    locked, release = asyncio.Event(), asyncio.Event()

    async def finish():
        async with fenced_transaction(engine, execution) as (conn, _, _):
            locked.set()
            await asyncio.wait_for(release.wait(), 5)
            await write_sample(conn, execution, owner)
            await execute(
                conn,
                "UPDATE monitor_runs SET state='succeeded',version=version+1,"
                "finished_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=execution.run_id.bytes,
            )

    task = asyncio.create_task(finish())
    await asyncio.wait_for(locked.wait(), 5)
    close = asyncio.create_task(
        configuration.patch(owner, MonitorPatch(expected_version=1, enabled=False), new_id())
    )
    assert not close.done()
    release.set()
    _, result = await asyncio.wait_for(asyncio.gather(task, close), 5)
    assert result.state == "disabled" and result.last_run.state == "succeeded"
    async with engine.connect() as conn:
        count = await first(
            conn,
            "SELECT COUNT(*) AS n FROM monitor_samples WHERE run_id=:id",
            id=execution.run_id.bytes,
        )
    assert count["n"] == 1
    print("结果先持锁提交与关闭并发：已提交样本保留，关闭事务随后生效：通过")


async def verify_credential_update(engine, crypto):
    owner = new_id()
    execution, credential = await running(engine, owner)
    configuration = MonitorConfiguration(engine, crypto)
    control = CredentialControls(engine)
    command = RevokeBarrier(
        owner_user_id=owner,
        request_id=new_id(),
        operation_id=new_id(),
        credential_ref=credential,
        expected_credential_version=1,
    )
    await control.prepare(command, revoke=False)
    view = await configuration.get(owner)
    assert view.state == "requires_reauth" and view.config.enabled
    saved = await configuration.patch(
        owner,
        MonitorPatch(
            expected_version=view.version, interval_minutes=75, email="test@example.invalid"
        ),
        new_id(),
    )
    assert saved.state == "requires_reauth" and saved.config.interval_minutes == 75
    proof = {
        "credential_ref": str(credential),
        "credential_version": 2,
        "state": "active",
        "use_allowed": True,
    }
    await control.commit(command, proof, revoke=False)
    view = await configuration.get(owner)
    assert view.state == "active" and view.config.interval_minutes == 75
    try:
        async with fenced_transaction(engine, execution):
            raise AssertionError("凭据变更前的执行仍可提交")
    except ApiError as error:
        assert error.code == ErrorCode.VERSION_CONFLICT
    print("凭据变更屏障、待认证仍可保存配置、新凭据恢复且旧执行失效：通过")
