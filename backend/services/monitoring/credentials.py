"""凭据更新/撤回在 Adapter 激活/撤销之前建立持久屏障。"""

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first

from .barriers import digest, operation_for, replay, result
from .repository import audit, invalidate, lock_monitor


class CredentialControls:
    def __init__(self, engine):
        self.engine = engine

    async def prepare(self, command, *, revoke):
        kind = "credential_revoke" if revoke else "credential_update"
        async with self.engine.begin() as conn:
            monitor = await lock_monitor(conn, command.owner_user_id)
            previous = await replay(conn, command, kind)
            if previous:
                return await result(conn, monitor, previous)
            if monitor["credential_operation_id"]:
                raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "已有凭据操作正在进行")
            if monitor["credential_version"] is not None and (
                monitor["credential_version"] != command.expected_credential_version
                or monitor["credential_ref"] != command.credential_ref.bytes
            ):
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "凭据版本已更新")
            await invalidate(conn, monitor)
            await execute(
                conn,
                "INSERT INTO control_operations (id,owner_user_id,type,credential_ref,"
                "credential_version,generation,state,request_digest) VALUES "
                "(:id,:owner,:kind,:ref,:version,:generation,'prepared',:digest)",
                id=command.operation_id.bytes,
                owner=command.owner_user_id.bytes,
                kind=kind,
                ref=command.credential_ref.bytes,
                version=command.expected_credential_version,
                generation=monitor["generation"] + 1,
                digest=digest(command),
            )
            state = (
                "retargeting"
                if monitor["state"] == "retargeting"
                else (
                    "requires_reauth" if monitor["desired_enabled"] and not revoke else "disabled"
                )
            )
            await execute(
                conn,
                "UPDATE monitors SET credential_operation_id=:operation,credential_allowed=0,"
                "credential_ref=:ref,credential_version=:version,desired_enabled=IF(:revoke,0,desired_enabled),"
                "state=:state,next_run_at=NULL,version=version+1,generation=generation+1,"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                operation=command.operation_id.bytes,
                ref=command.credential_ref.bytes,
                version=command.expected_credential_version,
                revoke=revoke,
                state=state,
                id=monitor["id"],
            )
            await audit(conn, monitor, command.request_id, f"monitor.{kind}_prepared")
            return await result(conn, monitor, await operation_for(conn, command, kind))

    async def commit(self, command, proof, *, revoke):
        kind = "credential_revoke" if revoke else "credential_update"
        async with self.engine.begin() as conn:
            monitor = await lock_monitor(conn, command.owner_user_id)
            operation = await replay(conn, command, kind)
            if not operation:
                raise ApiError(404, ErrorCode.NOT_FOUND, "凭据屏障不存在")
            if operation["state"] == "committed":
                return await result(conn, monitor, operation)
            expected = command.expected_credential_version + (not revoke)
            if (
                monitor["credential_operation_id"] != command.operation_id.bytes
                or proof.get("credential_ref") != str(command.credential_ref)
                or proof.get("credential_version") != expected
                or proof.get("state")
                not in ({"revoked"} if revoke else {"active", "requires_reauth"})
            ):
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "凭据尚未确认激活或撤销")
            allowed = (
                not revoke and proof.get("use_allowed") is True and proof.get("state") == "active"
            )
            state = monitor["state"]
            if state != "retargeting":
                state = "disabled"
                if monitor["desired_enabled"]:
                    state = "active" if allowed else "requires_reauth"
                    if not monitor["binding_id"]:
                        state = "blocked_room"
            await execute(
                conn,
                "UPDATE monitors SET credential_operation_id=NULL,credential_allowed=:allowed,"
                "credential_version=:version,state=:state,version=version+1,"
                "next_run_at=IF(:state='active',UTC_TIMESTAMP(6),NULL),updated_at=UTC_TIMESTAMP(6) "
                "WHERE id=:id",
                allowed=allowed,
                version=expected,
                state=state,
                id=monitor["id"],
            )
            await execute(
                conn,
                "UPDATE control_operations SET state='committed',updated_at=UTC_TIMESTAMP(6) "
                "WHERE id=:id",
                id=command.operation_id.bytes,
            )
            await audit(conn, monitor, command.request_id, f"monitor.{kind}_committed")
            return await result(conn, monitor, await operation_for(conn, command, kind))

    async def abort_update(self, command, proof):
        async with self.engine.begin() as conn:
            monitor = await lock_monitor(conn, command.owner_user_id)
            operation = await replay(conn, command, "credential_update")
            if not operation:
                raise ApiError(404, ErrorCode.NOT_FOUND, "凭据屏障不存在")
            if operation["state"] == "compensated":
                return await result(conn, monitor, operation)
            if operation["state"] != "prepared" or (
                proof.get("credential_version") != command.expected_credential_version
                or proof.get("credential_ref") not in {None, str(command.credential_ref)}
            ):
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "凭据已变化，不能补偿")
            allowed = proof.get("state") == "active" and proof.get("use_allowed") is True
            state = (
                "disabled"
                if not monitor["desired_enabled"]
                else ("active" if allowed and monitor["binding_id"] else "requires_reauth")
            )
            if monitor["state"] == "retargeting":
                state = "retargeting"
            await execute(
                conn,
                "UPDATE monitors SET credential_operation_id=NULL,credential_allowed=:allowed,"
                "state=:state,version=version+1,generation=generation+1,"
                "next_run_at=IF(:state='active',UTC_TIMESTAMP(6),NULL) WHERE id=:id",
                allowed=allowed,
                state=state,
                id=monitor["id"],
            )
            await execute(
                conn,
                "UPDATE control_operations SET state='compensated',generation=:generation "
                "WHERE id=:id",
                generation=monitor["generation"] + 1,
                id=operation["id"],
            )
            await audit(conn, monitor, command.request_id, "monitor.credential_update_compensated")
            return await result(
                conn, monitor, await operation_for(conn, command, "credential_update")
            )

    async def read(self, owner, operation):
        async with self.engine.connect() as conn:
            row = await first(
                conn,
                "SELECT * FROM control_operations WHERE id=:id AND owner_user_id=:owner "
                "AND type IN ('credential_revoke','credential_update')",
                id=operation.bytes,
                owner=owner.bytes,
            )
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "凭据屏障不存在")
        from uuid import UUID

        return {
            "operation_id": str(operation),
            "credential_ref": str(UUID(bytes=row["credential_ref"])),
            "expected_credential_version": row["credential_version"],
            "kind": row["type"],
            "state": row["state"],
        }
