"""学校绑定与默认子操作独立恢复；默认失败不能再提交学校绑定。"""

from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError

from .bindings import confirm, fail, finish_default
from .control_jobs import update


class BindingSaga:
    def __init__(self, engine, client):
        self.engine, self.client = engine, client

    async def advance(self, row, principal):
        if row["binding_status"] == "confirmed":
            if not await finish_default(self.engine, row):
                await update(self.engine, row, release=True)
            return
        command = {"owner_user_id": str(principal.user_id), "request_id": str(principal.request_id)}
        preparing = row["saga_step"] == "binding_prepared"
        if preparing:
            command.update(
                upstream_operation_id=str(UUID(bytes=row["upstream_operation_id"])),
                candidate_id=row["candidate_id"],
                credential_ref=str(UUID(bytes=row["credential_ref"])),
                credential_version=row["credential_version"],
            )
        else:
            command["operation_id"] = str(UUID(bytes=row["upstream_operation_id"]))
        try:
            value = await self.client.call(
                "school_adapter",
                "/upstream/bindings" if preparing else "/upstream/operations",
                "school:binding",
                principal.request_id,
                command,
                principal=principal,
            )
        except ApiError as error:
            if preparing and error.code in {
                ErrorCode.ROOM_CANDIDATE_EXPIRED,
                ErrorCode.NOT_FOUND,
                ErrorCode.INVALID_ARGUMENT,
                ErrorCode.SCHOOL_REAUTH_REQUIRED,
            }:
                await fail(self.engine, row, error.code)
                return
            raise
        if value["state"] == "confirmed":
            await confirm(self.engine, row, value["binding_record"], principal.request_id)
            if not await finish_default(self.engine, row):
                await update(self.engine, row, step="default_wait", release=True)
        elif value["state"] == "rejected":
            await fail(self.engine, row, value["error_code"])
        else:
            unknown = value["state"] == "unknown"
            await update(
                self.engine,
                row,
                step="binding_prepared" if value["state"] == "prepared" else "binding_reconciling",
                error=value["error_code"],
                state="unknown" if unknown else "reconciling",
                release=True,
                delay=300 if unknown else 30,
                binding_status="unknown" if unknown else "pending",
            )
