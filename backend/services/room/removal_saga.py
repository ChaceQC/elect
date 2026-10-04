"""默认先屏障、学校一次解绑、缺席确认后清本域默认，跨阶段持续恢复。"""

from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError

from .control_jobs import update
from .removals import commit, finish


class RemovalSaga:
    def __init__(self, engine, client):
        self.engine, self.client = engine, client

    async def barrier(self, path, row, principal, version=None):
        command = {
            "owner_user_id": str(principal.user_id),
            "request_id": str(principal.request_id),
            "operation_id": str(UUID(bytes=row["id"])),
            "target_binding_id": None,
        }
        command["committed_preference_version" if version else "expected_preference_version"] = (
            version or row["expected_preference_version"]
        )
        return await self.client.call(
            "monitoring",
            path,
            "monitor:retarget",
            principal.request_id,
            command,
            principal=principal,
        )

    async def fail(self, row, principal, error):
        await update(self.engine, row, step="compensating", state="reconciling", error=error)
        if row["removal_was_default"]:
            await self.barrier("/monitor/compensate-retarget", row, principal)
        await finish(self.engine, row, failed=True)

    async def advance(self, row, principal):
        if row["saga_step"] == "compensating":
            await self.fail(row, principal, row["error_code"])
            return
        if row["removal_was_default"]:
            await self.barrier("/monitor/prepare-retarget", row, principal)
        if row["binding_status"] != "removed":
            command = {
                "owner_user_id": str(principal.user_id),
                "request_id": str(principal.request_id),
            }
            preparing = row["saga_step"] == "removal_prepared"
            if preparing:
                from services.common.sql import first

                async with self.engine.connect() as conn:
                    target = await first(
                        conn,
                        "SELECT school_room_id FROM rooms WHERE id=:id",
                        id=row["target_room_id"],
                    )
                command.update(
                    upstream_operation_id=str(UUID(bytes=row["upstream_operation_id"])),
                    room_operation_id=str(UUID(bytes=row["id"])),
                    room_id=target["school_room_id"],
                    credential_ref=str(UUID(bytes=row["credential_ref"])),
                    credential_version=row["credential_version"],
                    lease_owner=row["lease_owner"],
                )
            else:
                command["operation_id"] = str(UUID(bytes=row["upstream_operation_id"]))
            try:
                value = await self.client.call(
                    "school_adapter",
                    "/upstream/removals" if preparing else "/upstream/operations",
                    "school:binding",
                    principal.request_id,
                    command,
                    principal=principal,
                )
            except ApiError as error:
                if preparing and error.code in {
                    ErrorCode.SCHOOL_REAUTH_REQUIRED,
                    ErrorCode.INVALID_ARGUMENT,
                    ErrorCode.NOT_FOUND,
                }:
                    await self.fail(row, principal, error.code)
                    return
                raise
            if value["state"] == "rejected":
                await self.fail(row, principal, value["error_code"])
                return
            if value["state"] != "confirmed":
                unknown = value["state"] == "unknown"
                await update(
                    self.engine,
                    row,
                    step="removal_prepared"
                    if value["state"] == "prepared"
                    else "removal_reconciling",
                    state="unknown" if unknown else "reconciling",
                    error=value["error_code"],
                    release=True,
                    delay=30 if value["error_code"] else 2,
                    binding_status="unknown" if unknown else "pending",
                )
                return
        version = await commit(self.engine, row, principal.request_id)
        if row["removal_was_default"]:
            await self.barrier("/monitor/commit-retarget", row, principal, version)
        await finish(self.engine, row)
