"""学校删除前自行回查 Room 租约/槽位及默认监控屏障。"""

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import RemovalProof


async def require_intent(state, principal, command):
    proof = RemovalProof.model_validate(
        await state.service_client.call(
            "room",
            "/controls/removal",
            "room:remove-read",
            principal.request_id,
            {"operation_id": str(command.room_operation_id), "lease_owner": command.lease_owner},
            principal=principal,
        )
    )
    if (
        not proof.can_dispatch
        or proof.upstream_operation_id != command.upstream_operation_id
        or proof.record.room_id != command.room_id
        or proof.credential_ref != command.credential_ref
        or proof.credential_version != command.credential_version
    ):
        raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "解绑意图或执行租约已变化")
    if proof.was_default:
        barrier = await state.service_client.call(
            "monitoring",
            "/monitor/retarget-barrier",
            "monitor:retarget-read",
            principal.request_id,
            {"operation_id": str(command.room_operation_id)},
            principal=principal,
        )
        if (
            barrier["state"] != "prepared"
            or barrier["target_binding_id"] is not None
            or barrier["expected_preference_version"] != proof.expected_preference_version
        ):
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "默认解绑监控屏障尚未确认")
    return proof
