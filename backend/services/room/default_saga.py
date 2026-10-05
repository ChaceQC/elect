"""Room prepare → Monitoring 屏障 → 偏好提交 → Monitoring 确认，可跨进程恢复。"""

from uuid import UUID

from services.common.audit_events import record_audit
from services.common.http import ApiError
from services.common.sql import execute

from .control_jobs import update
from .defaults import commit_preference
from .preference_store import locked_operation


class DefaultSaga:
    def __init__(self, engine, client):
        self.engine, self.client = engine, client

    async def finish(self, row, request_id, *, compensated=False):
        async with self.engine.begin() as conn:
            current = await locked_operation(conn, row)
            if not current:
                return
            await execute(
                conn,
                "UPDATE room_preferences SET "
                "state=IF(default_binding_id IS NULL,'blocked','ready'),"
                "switch_operation_id=NULL,updated_at=UTC_TIMESTAMP(6) "
                "WHERE owner_user_id=:owner AND switch_operation_id=:operation",
                owner=current["owner_user_id"],
                operation=current["id"],
            )
            await execute(
                conn,
                "UPDATE room_operations SET "
                "state=:state,saga_step=:step,lease_owner=NULL,lease_until=NULL,"
                "next_reconcile_at=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=current["id"],
                state="failed" if compensated else "succeeded",
                step="compensated" if compensated else "completed",
            )
            await record_audit(
                conn,
                "room",
                "room.default_compensated" if compensated else "room.default_succeeded",
                "operation",
                UUID(bytes=current["id"]),
                request_id,
                actor=UUID(bytes=current["owner_user_id"]),
                result="failed" if compensated else "succeeded",
            )
            from .sync_defaults import realign_after_switch

            await realign_after_switch(conn, UUID(bytes=current["owner_user_id"]), request_id)

    async def advance(self, row, principal):
        command = {
            "owner_user_id": str(principal.user_id),
            "request_id": str(principal.request_id),
            "operation_id": str(UUID(bytes=row["id"])),
            "target_binding_id": str(UUID(bytes=row["target_binding_id"]))
            if row["target_binding_id"] else None,
            "expected_preference_version": row["expected_preference_version"],
        }
        if row["saga_step"] == "compensating":
            await self.client.call(
                "monitoring",
                "/monitor/compensate-retarget",
                "monitor:retarget",
                principal.request_id,
                command,
                principal=principal,
            )
            await self.finish(row, principal.request_id, compensated=True)
            return
        await self.client.call(
            "monitoring",
            "/monitor/prepare-retarget",
            "monitor:retarget",
            principal.request_id,
            command,
            principal=principal,
        )
        await update(
            self.engine,
            row,
            step="monitor_prepared"
            if not row["committed_preference_version"]
            else row["saga_step"],
        )
        try:
            version = await commit_preference(self.engine, row, principal.request_id)
        except ApiError as error:
            if error.status not in {404, 409}:
                raise
            await update(
                self.engine, row, step="compensating", state="reconciling", error=error.code
            )
            await self.client.call(
                "monitoring",
                "/monitor/compensate-retarget",
                "monitor:retarget",
                principal.request_id,
                command,
                principal=principal,
            )
            await self.finish(row, principal.request_id, compensated=True)
            return
        commit = {
            key: value for key, value in command.items() if key != "expected_preference_version"
        }
        commit["committed_preference_version"] = version
        await self.client.call(
            "monitoring",
            "/monitor/commit-retarget",
            "monitor:retarget",
            principal.request_id,
            commit,
            principal=principal,
        )
        await self.finish(row, principal.request_id)
