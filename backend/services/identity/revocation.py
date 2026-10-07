"""撤回先持久受理，再建立 Monitoring 屏障、撤销 Adapter，最后确认完成。"""

from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import aware, execute, first


class Revocations:
    def __init__(self, engine, client):
        self.engine, self.client = engine, client

    async def accept(self, principal, expected):
        async with self.engine.connect() as conn:
            old = await first(
                conn,
                "SELECT id FROM credential_operations WHERE owner_user_id=:owner "
                "AND expected_credential_version=:version",
                owner=principal.user_id.bytes,
                version=expected,
            )
        if old:
            return UUID(bytes=old["id"])
        proof = await self.client.call(
            "school_adapter",
            "/credentials/control-view",
            "credential:control-read",
            principal.request_id,
            principal=principal,
        )
        async with self.engine.begin() as conn:
            user = await first(
                conn, "SELECT * FROM users WHERE id=:id FOR UPDATE", id=principal.user_id.bytes
            )
            old = await first(
                conn,
                "SELECT id FROM credential_operations WHERE owner_user_id=:owner "
                "AND expected_credential_version=:version",
                owner=principal.user_id.bytes,
                version=expected,
            )
            if old:
                return UUID(bytes=old["id"])
            if user["credential_operation_id"]:
                raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "凭据操作正在进行，请稍后刷新")
            if proof["credential_version"] != expected or (
                user["credential_version"] is not None and user["credential_version"] != expected
            ):
                raise ApiError(
                    409,
                    ErrorCode.VERSION_CONFLICT,
                    "凭据已变化，请刷新后重试",
                    current_version=user["credential_version"] or proof["credential_version"],
                )
            operation = new_id()
            await execute(
                conn,
                "INSERT INTO credential_operations "
                "(id,owner_user_id,credential_ref,expected_credential_version,state,saga_step,"
                "next_reconcile_at) VALUES (:id,:owner,:ref,:version,"
                "'accepted','accepted',UTC_TIMESTAMP(6))",
                id=operation.bytes,
                owner=principal.user_id.bytes,
                ref=user["credential_ref"],
                version=expected,
            )
            await execute(
                conn,
                "UPDATE users SET credential_operation_id=:operation,credential_version=:version,"
                "credential_status='revoking' WHERE id=:owner",
                operation=operation.bytes,
                owner=principal.user_id.bytes,
                version=expected,
            )
            await execute(
                conn,
                "UPDATE consents SET revoked_at=UTC_TIMESTAMP(6) WHERE user_id=:owner "
                "AND revoked_at IS NULL",
                owner=principal.user_id.bytes,
            )
            await record_audit(
                conn,
                "identity",
                "credential.revoke_accepted",
                "operation",
                operation,
                principal.request_id,
                actor=principal.user_id,
            )
            return operation

    async def operation(self, owner, operation):
        async with self.engine.connect() as conn:
            row = await first(
                conn,
                "SELECT * FROM credential_operations WHERE id=:id AND owner_user_id=:owner",
                id=operation.bytes,
                owner=owner.bytes,
            )
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "操作不存在")
        return {
            "id": str(operation),
            "type": "credential_revoke",
            "state": row["state"],
            "target_binding_id": None,
            "created_at": aware(row["created_at"]),
            "binding_status": None,
            "default_status": None,
            "retryable": bool(row["error_code"]),
            "error_code": row["error_code"],
            "next_reconcile_at": aware(row["next_reconcile_at"]),
            "result_binding_id": None,
            "result_order_id": None,
        }

    async def advance(self, row, request_id):
        operation, owner = UUID(bytes=row["id"]), UUID(bytes=row["owner_user_id"])
        principal = Principal("identity", owner, 1, request_id)
        command = {
            "operation_id": str(operation),
            "owner_user_id": str(owner),
            "request_id": str(request_id),
            "credential_ref": str(UUID(bytes=row["credential_ref"])),
            "expected_credential_version": row["expected_credential_version"],
        }
        stages = [
            ("monitoring", "/credentials/prepare-revoke", "monitor:credential", "barrier_prepared"),
            ("school_adapter", "/credentials/revoke", "credential:revoke", "adapter_revoked"),
            ("monitoring", "/credentials/commit-revoke", "monitor:credential", "monitor_committed"),
        ]
        # 每一步的接收方自身幂等；失去响应可重复确认，不能跳过未确认的屏障。
        for receiver, path, scope, step in stages:
            await self.client.call(receiver, path, scope, request_id, command, principal=principal)
            async with self.engine.begin() as conn:
                await execute(
                    conn,
                    "UPDATE credential_operations SET state='running',saga_step=:step,"
                    "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                    step=step,
                    id=row["id"],
                )
        async with self.engine.begin() as conn:
            await execute(
                conn,
                "UPDATE users SET credential_operation_id=NULL,credential_status='revoked' "
                "WHERE id=:owner AND credential_operation_id=:operation",
                owner=owner.bytes,
                operation=operation.bytes,
            )
            await execute(
                conn,
                "UPDATE credential_operations SET state='succeeded',saga_step='completed',"
                "error_code=NULL,next_reconcile_at=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=row["id"],
            )
            await record_audit(
                conn,
                "identity",
                "credential.revoked",
                "operation",
                operation,
                request_id,
                actor=owner,
            )


async def recover_revocation(app):
    async with app.state.database.connect() as conn:
        row = await first(
            conn,
            "SELECT * FROM credential_operations "
            "WHERE state IN ('accepted','running','reconciling') "
            "AND next_reconcile_at<=UTC_TIMESTAMP(6) ORDER BY next_reconcile_at LIMIT 1",
        )
    if not row:
        return False
    async with app.state.login_saga.locked(UUID(bytes=row["id"]), background=True):
        async with app.state.database.connect() as conn:
            current = await first(
                conn, "SELECT * FROM credential_operations WHERE id=:id", id=row["id"]
            )
        if current["state"] == "succeeded":
            return True
        try:
            await Revocations(app.state.database, app.state.service_client).advance(
                current, new_id()
            )
        except ApiError as error:
            async with app.state.database.begin() as conn:
                await execute(
                    conn,
                    "UPDATE credential_operations SET state='reconciling',error_code=:error,"
                    "next_reconcile_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 5 SECOND),"
                    "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                    error=error.code,
                    id=row["id"],
                )
            raise
    return True
