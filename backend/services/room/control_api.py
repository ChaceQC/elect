"""Monitoring 回查本域持久偏好提交证明，不接受调用方自报提交成功。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import OperationQuery, PreferenceProof, RemovalProofQuery
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
            "WHERE o.id=:id AND o.owner_user_id=:owner AND o.type IN ('switch_default',"
            "'unbind_room')",
            id=command.operation_id.bytes,
            owner=principal.user_id.bytes,
        )
    if not operation:
        raise ApiError(404, ErrorCode.NOT_FOUND, "偏好操作不存在")
    version = operation["committed_preference_version"]
    target = None if operation["type"] == "unbind_room" else operation["target_binding_id"]
    committed = (
        version is not None
        and operation["actual_version"] == version
        and operation["actual_binding_id"] == target
        and operation["saga_step"] in {"preference_committed", "monitor_committed", "completed"}
    )
    return PreferenceProof(
        operation_id=command.operation_id,
        binding_id=UUID(bytes=target) if target else None,
        preference_version=version,
        committed=committed,
        can_compensate=version is None
        and operation["state"] in {"reconciling", "failed", "cancelled"}
        and operation["saga_step"] in {"compensating", "compensated"},
    )


@router.post("/removal")
async def removal_proof(
    command: RemovalProofQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("room:remove-read"))],
):
    async with request.app.state.database.connect() as conn:
        row = await first(
            conn,
            "SELECT o.*,r.school_room_id,r.building_name,r.room_no,r.meter_code,"
            "b.school_relation_id,p.removal_operation_id,"
            "(o.lease_owner=:lease AND o.lease_until>UTC_TIMESTAMP(6)) AS lease_valid "
            "FROM room_operations o JOIN rooms r ON r.id=o.target_room_id "
            "JOIN room_bindings b ON b.id=o.target_binding_id AND b.owner_user_id=o.owner_user_id "
            "JOIN room_preferences p ON p.owner_user_id=o.owner_user_id "
            "WHERE o.id=:id AND o.owner_user_id=:owner AND o.type='unbind_room'",
            id=command.operation_id.bytes,
            owner=principal.user_id.bytes,
            lease=command.lease_owner,
        )
    if not row:
        raise ApiError(404, ErrorCode.NOT_FOUND, "解绑操作不存在")
    return {
        "room_operation_id": str(command.operation_id),
        "upstream_operation_id": str(UUID(bytes=row["upstream_operation_id"])),
        "record": {
            "room_id": row["school_room_id"],
            "building": row["building_name"],
            "number": row["room_no"],
            "display_name": row["building_name"] + " " + row["room_no"],
            "balance": None,
            "meter_code": row["meter_code"],
            "relation_id": row["school_relation_id"],
        },
        "was_default": bool(row["removal_was_default"]),
        "expected_preference_version": row["expected_preference_version"],
        "credential_ref": str(UUID(bytes=row["credential_ref"])),
        "credential_version": row["credential_version"],
        "can_dispatch": bool(
            row["lease_valid"]
            and row["removal_operation_id"] == row["id"]
            and row["state"] in {"running", "reconciling", "unknown"}
            and row["binding_status"] != "removed"
            and row["saga_step"] != "compensating"
        ),
    }
