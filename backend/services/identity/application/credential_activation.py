"""已验证登录的三域激活协调；每用户槽位阻止登录与撤回互相覆盖。"""

from uuid import UUID

from services.common.http import ApiError
from services.common.security import Principal
from services.common.sql import execute


class CredentialActivation:
    def __init__(self, engine, client):
        self.engine, self.client = engine, client

    async def activate(self, row, request_id):
        owner, attempt = UUID(bytes=row["user_id"]), UUID(bytes=row["id"])
        principal = Principal("identity", owner, 1, request_id)
        barrier = {
            "owner_user_id": str(owner),
            "request_id": str(request_id),
            "operation_id": str(attempt),
            "credential_ref": str(UUID(bytes=row["credential_ref"])),
            "expected_credential_version": row["expected_credential_version"] or 0,
        }
        await self.client.call(
            "monitoring",
            "/credentials/prepare-update",
            "monitor:credential",
            request_id,
            barrier,
            principal=principal,
        )
        try:
            await self.client.call(
                "school_adapter",
                "/credentials/activate",
                "credential:activate",
                request_id,
                {
                    "attempt_id": str(attempt),
                    "owner_user_id": str(owner),
                    "request_id": str(request_id),
                    "credential_ref": barrier["credential_ref"],
                    "expected_credential_version": row["expected_credential_version"],
                    "credential_use_allowed": bool(row["credential_use_allowed"]),
                },
                principal=principal,
            )
        except ApiError as error:
            if error.status >= 500 or error.status == 429:
                raise
            proof = await self.client.call(
                "school_adapter",
                "/credentials/control-view",
                "credential:control-read",
                request_id,
                principal=principal,
            )
            if proof["credential_version"] != row["credential_version"]:
                await self.client.call(
                    "monitoring",
                    "/credentials/abort-update",
                    "monitor:credential",
                    request_id,
                    barrier,
                    principal=principal,
                )
                await self.finalize(row, proof["credential_version"], proof["state"], failed=True)
                raise
        await self.client.call(
            "monitoring",
            "/credentials/commit-update",
            "monitor:credential",
            request_id,
            barrier,
            principal=principal,
        )
        await self.finalize(row, row["credential_version"], "active")

    async def finalize(self, row, version, status, *, failed=False):
        async with self.engine.begin() as conn:
            await execute(
                conn,
                "UPDATE users SET credential_operation_id=NULL,credential_version=:version,"
                "credential_status=:status WHERE id=:user AND credential_operation_id=:attempt",
                user=row["user_id"],
                attempt=row["id"],
                version=version or None,
                status=status,
            )
            await execute(
                conn,
                "UPDATE login_attempts SET state=:state,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                state="failed" if failed else "activated",
                id=row["id"],
            )
