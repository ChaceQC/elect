"""一次绑定写入的 MySQL 权威台账，缓存和进程重启不能重置 dispatched。"""

import hashlib
import json
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import aware, execute, first

from .rooms import room_record


def digest(command):
    value = command.model_dump(mode="json", exclude={"request_id"})
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).digest()


def aad(owner, operation):
    return f"binding:{owner}:{operation}"


def result(row):
    record = row["confirmed_record"]
    return {
        "upstream_operation_id": str(UUID(bytes=row["id"])),
        "state": row["state"],
        "dispatched_at": aware(row["dispatched_at"]),
        "result_ref": None,
        "error_code": row["error_code"],
        "binding_record": json.loads(record) if isinstance(record, str) else record,
    }


class BindingLedger:
    def __init__(self, engine, crypto):
        self.engine, self.crypto = engine, crypto

    async def get(self, owner, operation):
        async with self.engine.connect() as conn:
            return await first(
                conn,
                "SELECT * FROM upstream_operations WHERE id=:id "
                "AND owner_user_id=:owner AND operation_type='bind_room'",
                id=operation.bytes,
                owner=owner.bytes,
            )

    @staticmethod
    def replay(row, command):
        if row and row["request_digest"] != digest(command):
            raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "上游编号已用于不同绑定请求")
        return row

    async def prepare(self, command, value):
        record = room_record(value["record"])
        async with self.engine.begin() as conn:
            credential = await self.lock_credential(conn, command)
            row = await first(
                conn,
                "SELECT * FROM upstream_operations WHERE id=:id FOR UPDATE",
                id=command.upstream_operation_id.bytes,
            )
            if row:
                if row["owner_user_id"] != command.owner_user_id.bytes:
                    raise ApiError(404, ErrorCode.NOT_FOUND, "上游操作不存在")
                return self.replay(row, command)
            pending = await first(
                conn,
                "SELECT id FROM upstream_operations WHERE owner_user_id=:owner "
                "AND open_binding_target=:target",
                owner=command.owner_user_id.bytes,
                target=record["room_id"],
            )
            if pending:
                raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "该目标有尚未解决的学校绑定")
            await execute(
                conn,
                "INSERT INTO upstream_operations (id,owner_user_id,operation_type,"
                "target_ref,request_digest,credential_version,state,candidate_ciphertext) "
                "VALUES (:id,:owner,'bind_room',:target,:digest,:version,'prepared',:candidate)",
                id=command.upstream_operation_id.bytes,
                owner=command.owner_user_id.bytes,
                target=record["room_id"],
                digest=digest(command),
                version=credential["version"],
                candidate=self.crypto.seal(
                    value, aad(command.owner_user_id, command.upstream_operation_id)
                ),
            )
        return await self.get(command.owner_user_id, command.upstream_operation_id)

    async def lock_credential(self, conn, command):
        row = await first(
            conn,
            "SELECT * FROM school_credentials WHERE owner_user_id=:owner FOR UPDATE",
            owner=command.owner_user_id.bytes,
        )
        if (
            not row
            or row["id"] != command.credential_ref.bytes
            or (
                row["version"] != command.credential_version
                or row["status"] != "active"
                or not row["use_allowed"]
            )
        ):
            raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化，请重新确认绑定")
        return row

    async def reserve(self, command):
        async with self.engine.begin() as conn:
            await self.lock_credential(conn, command)
            row = await first(
                conn,
                "SELECT * FROM upstream_operations WHERE id=:id FOR UPDATE",
                id=command.upstream_operation_id.bytes,
            )
            if not row or row["state"] != "prepared":
                return False
            await execute(
                conn,
                "UPDATE upstream_operations SET state='dispatched',"
                "dispatched_at=UTC_TIMESTAMP(6),error_code=NULL,updated_at=UTC_TIMESTAMP(6) "
                "WHERE id=:id",
                id=row["id"],
            )
            await record_audit(
                conn,
                "school_adapter",
                "school.binding_dispatched",
                "operation",
                command.upstream_operation_id,
                command.request_id,
                actor=command.owner_user_id,
            )
            return True

    async def settle(self, owner, operation, request_id, *, record=None, rejected=None, error=None):
        async with self.engine.begin() as conn:
            row = await first(
                conn,
                "SELECT * FROM upstream_operations WHERE id=:id "
                "AND owner_user_id=:owner FOR UPDATE",
                id=operation.bytes,
                owner=owner.bytes,
            )
            if row["state"] in {"confirmed", "rejected"}:
                return result(row)
            terminal = record is not None or rejected is not None
            state = (
                "confirmed"
                if record
                else "rejected"
                if rejected
                else "prepared"
                if not row["dispatched_at"]
                else "reconciling"
            )
            await execute(
                conn,
                "UPDATE upstream_operations SET state=IF(:state='reconciling' "
                "AND dispatched_at<=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 10 MINUTE),"
                "'unknown',:state),"
                "confirmed_record=:record,error_code=:error,"
                "candidate_ciphertext=IF(:terminal,NULL,candidate_ciphertext),"
                "reconcile_at=IF(:terminal,NULL,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND)),"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                state=state,
                record=json.dumps(record, ensure_ascii=False) if record else None,
                error=rejected or error,
                terminal=terminal,
                id=operation.bytes,
            )
            if terminal:
                await record_audit(
                    conn,
                    "school_adapter",
                    f"school.binding_{state}",
                    "operation",
                    operation,
                    request_id,
                    actor=owner,
                    result="succeeded" if record else "failed",
                )
        return result(await self.get(owner, operation))
