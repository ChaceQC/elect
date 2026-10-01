import hashlib
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .queries import RoomQueries


class RoomRepository(RoomQueries):
    def __init__(self, engine):
        self.engine = engine

    async def accept_sync(self, owner, key):
        digest = hashlib.sha256(key.encode()).digest()
        async with self.engine.begin() as conn:
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

    async def claim(self):
        lease = str(new_id())
        async with self.engine.begin() as conn:
            row = await first(
                conn,
                "SELECT * FROM room_operations WHERE type='binding_sync' "
                "AND (state='accepted' OR (state='running' AND lease_until <= "
                "UTC_TIMESTAMP(6))) ORDER BY created_at,id LIMIT 1 "
                "FOR UPDATE SKIP LOCKED",
            )
            if not row:
                return None
            await execute(
                conn,
                "UPDATE room_operations SET state='running',lease_owner=:lease,"
                "lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 120 SECOND),"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                lease=lease,
                id=row["id"],
            )
            return {**row, "lease_owner": lease}

    async def complete(self, operation, records, error, request_id):
        owner = operation["owner_user_id"]
        async with self.engine.begin() as conn:
            row = await first(
                conn,
                "SELECT * FROM room_operations WHERE id=:id AND lease_owner=:lease "
                "AND lease_until>UTC_TIMESTAMP(6) AND state='running' FOR UPDATE",
                id=operation["id"],
                lease=operation["lease_owner"],
            )
            if not row:
                return False
            state = await first(
                conn,
                "SELECT * FROM room_sync_state WHERE owner_user_id=:owner FOR UPDATE",
                owner=owner,
            )
            if error:
                sync_state = "stale" if state["last_synced_at"] else "failed"
                await execute(
                    conn,
                    "UPDATE room_balance_cache c JOIN room_bindings b "
                    "ON c.binding_id=b.id SET c.quality='stale',c.error_code=:error "
                    "WHERE b.owner_user_id=:owner",
                    error=error,
                    owner=owner,
                )
            else:
                sync_state = await self.mirror(conn, owner, records)
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
                "error_code=:error,lease_owner=NULL,lease_until=NULL,next_reconcile_at=NULL,"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                state="failed" if error else "succeeded",
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

    async def mirror(self, conn, owner, records):
        previous = (
            (
                await execute(
                    conn,
                    "SELECT id,room_id FROM room_bindings WHERE owner_user_id=:owner",
                    owner=owner,
                )
            )
            .mappings()
            .all()
        )
        seen = set()
        for record in records:
            await execute(
                conn,
                "INSERT INTO rooms (id,school_id,school_room_id,building_name,room_no,"
                "meter_code,metadata_version) VALUES (:id,'hbue',:school,:building,:number,"
                ":meter,1) ON DUPLICATE KEY UPDATE building_name=:building,room_no=:number,"
                "meter_code=:meter,updated_at=UTC_TIMESTAMP(6)",
                id=new_id().bytes,
                school=record["room_id"],
                building=record["building"],
                number=record["number"],
                meter=record["meter_code"],
            )
            room = await first(
                conn,
                "SELECT id FROM rooms WHERE school_id='hbue' AND school_room_id=:id",
                id=record["room_id"],
            )
            await execute(
                conn,
                "INSERT INTO room_bindings (id,owner_user_id,room_id,school_relation_id,"
                "status,last_confirmed_at) VALUES (:id,:owner,:room,:relation,'active',"
                "UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE status='active',"
                "school_relation_id=:relation,last_confirmed_at=UTC_TIMESTAMP(6),"
                "updated_at=UTC_TIMESTAMP(6)",
                id=new_id().bytes,
                owner=owner,
                room=room["id"],
                relation=record["relation_id"],
            )
            binding = await first(
                conn,
                "SELECT id FROM room_bindings WHERE owner_user_id=:owner AND room_id=:room",
                owner=owner,
                room=room["id"],
            )
            seen.add(binding["id"])
            await execute(
                conn,
                "INSERT INTO room_balance_cache (binding_id,balance,fetched_at,"
                "source,quality) VALUES (:id,:balance,UTC_TIMESTAMP(6),'school_bound_rooms',"
                "'fresh') ON DUPLICATE KEY UPDATE balance=:balance,fetched_at=UTC_TIMESTAMP(6),"
                "quality='fresh',error_code=NULL,updated_at=UTC_TIMESTAMP(6)",
                id=binding["id"],
                balance=record["balance"],
            )
        missing = [row["id"] for row in previous if row["id"] not in seen]
        for binding in missing:
            await execute(
                conn,
                "UPDATE room_bindings SET status='rechecking',updated_at=UTC_TIMESTAMP(6)"
                " WHERE id=:id",
                id=binding,
            )
            await execute(
                conn,
                "UPDATE room_balance_cache SET quality='stale',"
                "updated_at=UTC_TIMESTAMP(6) WHERE binding_id=:id",
                id=binding,
            )
        return "stale" if missing else "ready" if records else "empty"
