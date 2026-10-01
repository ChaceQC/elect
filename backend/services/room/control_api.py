"""Monitoring 回查本域持久偏好提交证明，不接受调用方自报提交成功。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import OperationQuery, PreferenceProof
from services.common.security import Principal, require_user_principal
from services.common.sql import first

router = APIRouter(prefix="/internal/v1/controls")
Control = Annotated[Principal, Depends(require_user_principal("room:control"))]


@router.post("/preference")
async def preference(command: OperationQuery, request: Request, principal: Control):
    async with request.app.state.database.connect() as conn:
        operation = await first(
            conn,
            "SELECT o.*,p.default_binding_id AS actual_binding_id,p.version AS actual_version "
            "FROM room_operations o LEFT JOIN room_preferences p "
            "ON p.owner_user_id=o.owner_user_id "
            "WHERE o.id=:id AND o.owner_user_id=:owner AND o.type='switch_default'",
            id=command.operation_id.bytes,
            owner=principal.user_id.bytes,
        )
    if not operation:
        raise ApiError(404, ErrorCode.NOT_FOUND, "偏好操作不存在")
    version = operation["committed_preference_version"]
    committed = (
        version is not None
        and operation["actual_version"] == version
        and operation["actual_binding_id"] == operation["target_binding_id"]
        and operation["saga_step"] in {"preference_committed", "monitor_committed", "completed"}
    )
    return PreferenceProof(
        operation_id=command.operation_id,
        binding_id=UUID(bytes=operation["target_binding_id"])
        if operation["target_binding_id"]
        else None,
        preference_version=version,
        committed=committed,
        can_compensate=version is None
        and operation["state"] in {"reconciling", "failed", "cancelled"}
        and operation["saga_step"] in {"compensating", "compensated"},
    )
