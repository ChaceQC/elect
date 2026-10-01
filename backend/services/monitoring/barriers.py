"""持久默认切换协议；Room 的提交证明由内部 API 查询后传入。"""

import hashlib
import json
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first

from .repository import audit, in_flight, invalidate, lock_monitor


def digest(command):
    value = command.model_dump(mode="json", exclude={"request_id"})
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).digest()


async def replay(conn, command, kind):
    row = await first(
        conn,
        "SELECT * FROM control_operations WHERE id=:id FOR UPDATE",
        id=command.operation_id.bytes,
    )
    if row and (
        row["owner_user_id"] != command.owner_user_id.bytes
        or row["type"] != kind
        or row["request_digest"] != digest(command)
    ):
        raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "操作编号已用于不同请求")
    return row


async def result(conn, monitor, operation):
    count, _ = await in_flight(conn, monitor)
    return {
        "operation_id": str(UUID(bytes=operation["id"])),
        "monitor_id": str(UUID(bytes=monitor["id"])),
        "generation": operation["generation"],
        "state": operation["state"],
        "cancel_pending": bool(count),
        "in_flight_count": count,
    }


async def operation_for(conn, command, kind):
    operation = await first(
        conn,
        "SELECT * FROM control_operations WHERE id=:id AND owner_user_id=:owner FOR UPDATE",
        id=command.operation_id.bytes,
        owner=command.owner_user_id.bytes,
    )
    if not operation or operation["type"] != kind:
        raise ApiError(404, ErrorCode.NOT_FOUND, "控制操作不存在")
    return operation


class RetargetControls:
    def __init__(self, engine):
        self.engine = engine

    async def prepare(self, command):
        async with self.engine.begin() as conn:
            monitor = await lock_monitor(conn, command.owner_user_id)
            previous = await replay(conn, command, "retarget")
            if previous:
                return await result(conn, monitor, previous)
            if monitor["state"] == "retargeting" or monitor["credential_operation_id"]:
                raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "已有控制操作正在进行")
            if monitor["preference_version"] is not None and (
                monitor["preference_version"] != command.expected_preference_version
            ):
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "默认偏好已变化")
            await invalidate(conn, monitor)
            await execute(
                conn,
                "INSERT INTO control_operations (id,owner_user_id,type,target_binding_id,"
                "previous_binding_id,expected_preference_version,generation,state,request_digest) "
                "VALUES (:id,:owner,'retarget',:target,:previous,:version,"
                ":generation,'prepared',:digest)",
                id=command.operation_id.bytes,
                owner=command.owner_user_id.bytes,
                target=command.target_binding_id.bytes if command.target_binding_id else None,
                previous=monitor["binding_id"],
                version=command.expected_preference_version,
                generation=monitor["generation"] + 1,
                digest=digest(command),
            )
            await execute(
                conn,
                "UPDATE monitors SET state='retargeting',next_run_at=NULL,"
                "version=version+1,generation=generation+1,last_retarget_operation_id=:operation,"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=monitor["id"],
                operation=command.operation_id.bytes,
            )
            await audit(conn, monitor, command.request_id, "monitor.retarget_prepared")
            return await result(conn, monitor, await operation_for(conn, command, "retarget"))

    async def finish(self, command, proof, *, compensate=False):
        async with self.engine.begin() as conn:
            monitor = await lock_monitor(conn, command.owner_user_id)
            operation = await operation_for(conn, command, "retarget")
            self.validate_finish(command, operation, proof, compensate)
            target_state = "compensated" if compensate else "committed"
            if operation["state"] == target_state:
                return await result(conn, monitor, operation)
            if operation["state"] != "prepared" or (
                monitor["last_retarget_operation_id"] != operation["id"]
            ):
                raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "切换已终结或已被其他操作替代")
            target = (
                operation["previous_binding_id"] if compensate else operation["target_binding_id"]
            )
            state = "disabled"
            if monitor["desired_enabled"]:
                state = "active" if monitor["credential_allowed"] else "requires_reauth"
                if target is None:
                    state = "blocked_room"
            version = (
                operation["expected_preference_version"]
                if compensate
                else command.committed_preference_version
            )
            # 再次建立新代次，补偿不能复活 prepare 之前的任务。
            await invalidate(conn, monitor)
            await execute(
                conn,
                "UPDATE monitors SET binding_id=:target,preference_version=:version,state=:state,"
                "generation=generation+1,version=version+1,last_sample_id=NULL,"
                "schedule_anchor_at=IF(:state='active',UTC_TIMESTAMP(6),schedule_anchor_at),"
                "next_run_at=IF(:state='active',UTC_TIMESTAMP(6),NULL),updated_at=UTC_TIMESTAMP(6) "
                "WHERE id=:id",
                target=target,
                version=version,
                state=state,
                id=monitor["id"],
            )
            await execute(
                conn,
                "UPDATE control_operations SET state=:state,committed_preference_version=:version,"
                "generation=:generation,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                state=target_state,
                version=version,
                generation=monitor["generation"] + 1,
                id=operation["id"],
            )
            await audit(conn, monitor, command.request_id, f"monitor.retarget_{target_state}")
            return await result(conn, monitor, await operation_for(conn, command, "retarget"))

    @staticmethod
    def validate_finish(command, operation, proof, compensate):
        if operation["target_binding_id"] != (
            command.target_binding_id.bytes if command.target_binding_id else None
        ):
            raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "切换目标与原操作不一致")
        expected = operation["expected_preference_version"]
        # 终态重放只验证原请求，不因后来其他 Saga 更新了 Room 偏好而改变旧结果。
        if operation["state"] == ("compensated" if compensate else "committed"):
            version = (
                command.expected_preference_version
                if compensate
                else command.committed_preference_version
            )
            if version != (expected if compensate else operation["committed_preference_version"]):
                raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "切换版本与原操作不一致")
            return
        if compensate:
            valid = (
                command.expected_preference_version == expected
                and proof.get("can_compensate") is True
            )
        else:
            valid = (
                command.committed_preference_version == expected + 1
                and proof.get("committed") is True
                and proof.get("preference_version") == command.committed_preference_version
                and proof.get("binding_id")
                == (str(command.target_binding_id) if command.target_binding_id else None)
            )
        if not valid or proof.get("operation_id") != str(command.operation_id):
            raise ApiError(409, ErrorCode.VERSION_CONFLICT, "Room 尚未确认此偏好提交状态")
