"""补偿与事务失败：已提交的默认不能补偿，未提交补偿采用新代次。"""

from scripts.t3_control_fixtures import assert_no_sample, running
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import CommitRetarget, PrepareRetarget
from services.monitoring.barriers import RetargetControls
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.fences import fenced_transaction


async def verify_compensation(engine, crypto):
    owner = new_id()
    execution, _ = await running(engine, owner)
    command = PrepareRetarget(
        owner_user_id=owner,
        request_id=new_id(),
        operation_id=new_id(),
        target_binding_id=new_id(),
        expected_preference_version=1,
    )
    controls = RetargetControls(engine)
    await controls.prepare(command)
    proof = {"operation_id": str(command.operation_id), "can_compensate": False}
    try:
        await controls.finish(command, proof, compensate=True)
    except ApiError as error:
        assert error.status == 409
    else:
        raise AssertionError("未经 Room 明确终止就补偿")
    proof["can_compensate"] = True
    result = await controls.finish(command, proof, compensate=True)
    assert result["state"] == "compensated" and result["generation"] == 3
    assert await controls.finish(command, proof, compensate=True) == result
    view = await MonitorConfiguration(engine, crypto).get(owner)
    assert view.binding_id == execution.binding_id and view.state == "active"
    try:
        async with fenced_transaction(engine, execution):
            raise AssertionError("补偿复活旧执行")
    except ApiError as error:
        assert error.status == 409
    # 同一个已补偿操作不能随后提交新目标。
    commit = CommitRetarget(
        owner_user_id=owner,
        request_id=new_id(),
        operation_id=command.operation_id,
        target_binding_id=command.target_binding_id,
        committed_preference_version=2,
    )
    try:
        await controls.finish(
            commit,
            {
                "operation_id": str(command.operation_id),
                "committed": True,
                "binding_id": str(command.target_binding_id),
                "preference_version": 2,
            },
        )
    except ApiError as error:
        assert error.status == 409
    else:
        raise AssertionError("补偿终态被覆盖")
    await assert_no_sample(engine, execution.run_id)
    print("补偿证明、重复补偿与终态冲突、新代次恢复原目标且旧执行不复活：通过")


async def verify_transaction_rollback(engine, crypto):
    from services.monitoring import configuration

    owner = new_id()
    execution, _ = await running(engine, owner)
    original = configuration.audit

    async def fail_outbox(*args):
        raise RuntimeError("synthetic outbox failure")

    configuration.audit = fail_outbox
    try:
        try:
            await MonitorConfiguration(engine, crypto).patch(
                owner, MonitorPatch(expected_version=1, enabled=False), new_id()
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Outbox 失败仍返回成功")
    finally:
        configuration.audit = original
    view = await MonitorConfiguration(engine, crypto).get(owner)
    assert view.version == 1 and view.generation == 1 and view.state == "active"
    async with fenced_transaction(engine, execution):
        pass
    print("Outbox 失败时配置、代次和运行取消同事务回滚：通过")
