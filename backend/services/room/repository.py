import hashlib
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .mirror import mirror_bindings
from .preference_store import lock_preference, locked_operation, require_no_removal
from .queries import RoomQueries
from .sync_defaults import align_default, snapshot_target


class RoomRepository(RoomQueries):
    def __init__(self, engine):
        self.engine = engine

    async def accept_sync(self, owner, key):
        digest = hashlib.sha256(key.encode()).digest()
        async with self.engine.begin() as conn:
            require_no_removal(await lock_preference(conn, owner))
            await execute(
                conn,
                "INSERT IGNORE INTO room_sync_state (owner_user_id,state) "
                "VALUES (:owner,'loading')",
                owner=owner.bytes,
            )
            await first(
                conn,
                "SELECT owner_user_id FROM room_sync_state WHERE owner_user_id=:owner FOR UPDATE",
                owner=owner.bytes,
            )
            row = await first(
                conn,
                "SELECT id FROM room_operations WHERE owner_user_id=:owner "
                "AND type='binding_sync' AND idempotency_key_hash=:key",
                owner=owner.bytes,
                key=digest,
            )
            if row:
                return UUID(bytes=row["id"])
            pending = await first(
                conn,
                "SELECT id FROM room_operations WHERE owner_user_id=:owner "
                "AND type='binding_sync' AND state IN ('accepted','running')",
                owner=owner.bytes,
            )
            if pending:
                raise ApiError(
                    409, ErrorCode.OPERATION_IN_PROGRESS, "寝室同步正在进行，请等待当前结果"
                )
            operation = new_id()
            await execute(
                conn,
                "INSERT INTO room_operations (id,owner_user_id,type,"
                "idempotency_key_hash,request_digest,state,saga_step,next_reconcile_at) "
                "VALUES (:id,:owner,'binding_sync',:key,:digest,'accepted','read_school',"
                "UTC_TIMESTAMP(6))",
                id=operation.bytes,
                owner=owner.bytes,
                key=digest,
                digest=hashlib.sha256(b"binding_sync").digest(),
            )
            await execute(
                conn,
                "UPDATE room_sync_state SET state='loading',error_code=NULL,"
                "updated_at=UTC_TIMESTAMP(6) WHERE owner_user_id=:owner",
                owner=owner.bytes,
            )
            await execute(
                conn,
                "INSERT IGNORE INTO room_preferences (owner_user_id,version,state) "
                "VALUES (:owner,1,'ready')",
                owner=owner.bytes,
            )
            return operation

    async def claim(self, schedule=None, *, stop=None):
        from .read_claims import claim_operation

        return await claim_operation(self.engine, "binding_sync", schedule, stop=stop)

    async def complete(self, operation, records, error, request_id, observation=None):
        from .balance_store import update_balances

        owner = operation["owner_user_id"]
        async with self.engine.begin() as conn:
            row = await locked_operation(conn, operation)
            if not row:
                return False
            state = await first(
                conn,
                "SELECT * FROM room_sync_state WHERE owner_user_id=:owner FOR UPDATE",
                owner=owner,
            )
            target = None
            if error:
                sync_state = "stale" if state["last_synced_at"] else "failed"
            else:
                sync_state = await mirror_bindings(conn, owner, records)
                target = await snapshot_target(conn, UUID(bytes=owner), records)
                await align_default(conn, UUID(bytes=owner), target, request_id)
            await update_balances(conn, owner, records, error, observation)
            await execute(
                conn,
                "UPDATE room_sync_state SET state=:state,error_code=:error,"
                "last_synced_at=IF(:success,UTC_TIMESTAMP(6),last_synced_at),"
                "updated_at=UTC_TIMESTAMP(6) WHERE owner_user_id=:owner",
                state=sync_state,
                error=error,
                success=error is None,
                owner=owner,
            )
            await execute(
                conn,
                "UPDATE room_operations SET state=:state,saga_step='complete',"
                "target_binding_id=IF(:success,:target,target_binding_id),"
                "error_code=:error,lease_owner=NULL,lease_until=NULL,next_reconcile_at=NULL,"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                state="failed" if error else "succeeded",
                success=error is None,
                target=target.bytes if error is None and target else None,
                error=error,
                id=operation["id"],
            )
            await record_audit(
                conn,
                "room",
                "room.bindings_synced",
                "operation",
                UUID(bytes=operation["id"]),
                request_id,
                actor=UUID(bytes=owner),
                result="failed" if error else "succeeded",
            )
        return True
