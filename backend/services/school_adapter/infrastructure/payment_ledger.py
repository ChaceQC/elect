"""D01 dispatched 永久保留；学校订单/URL/观察只存密文。"""

import hashlib
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first


def aad(owner, order, purpose="order"):
    return f"payment:{purpose}:{owner}:{order}"


def digest(command):
    return hashlib.sha256(
        command.model_dump_json(exclude={"request_id", "operation_id", "lease_owner"}).encode()
    ).digest()


class PaymentLedger:
    def __init__(self, state):
        self.state, self.engine = state, state.database
        self.crypto = state.school_credentials.crypto

    async def get(self, owner, order):
        async with self.engine.connect() as conn:
            row = await first(
                conn,
                "SELECT p.*,u.state,u.dispatched_at,u.request_digest,u.error_code "
                "FROM adapter_payment_orders p JOIN upstream_operations u "
                "ON u.id=p.upstream_operation_id WHERE p.order_id=:id AND p.owner_user_id=:owner",
                id=order.bytes,
                owner=owner.bytes,
            )
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "学校订单台账不存在")
        return row

    async def proof(self, command, principal):
        value = await self.state.service_client.call(
            "payment",
            "/controls/dispatch-proof",
            "payment:proof",
            command.request_id,
            {
                "order_id": str(command.order_id),
                "operation_id": str(command.operation_id),
                "lease_owner": command.lease_owner,
            },
            principal=principal,
        )
        if not value["can_dispatch"] or value["upstream_operation_id"] != str(
            command.upstream_operation_id
        ):
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "支付执行租约或订单状态已变化")
        return value

    async def credential(self, conn, command):
        row = await first(
            conn,
            "SELECT * FROM school_credentials WHERE owner_user_id=:owner FOR UPDATE",
            owner=command.owner_user_id.bytes,
        )
        if (
            not row
            or row["id"] != command.credential_ref.bytes
            or row["version"] != command.credential_version
            or row["status"] != "active"
            or not row["use_allowed"]
        ):
            raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校授权已变化")
        return row

    async def prepare(self, command, payload):
        async with self.engine.begin() as conn:
            await self.credential(conn, command)
            prior = await first(
                conn,
                "SELECT request_digest,owner_user_id FROM upstream_operations "
                "WHERE id=:id FOR UPDATE",
                id=command.upstream_operation_id.bytes,
            )
            if prior:
                if prior["owner_user_id"] != command.owner_user_id.bytes or prior[
                    "request_digest"
                ] != digest(command):
                    raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "上游支付编号已使用")
                return
            await execute(
                conn,
                "INSERT INTO upstream_operations (id,owner_user_id,operation_type,"
                "target_ref,request_digest,credential_version,state) "
                "VALUES (:id,:owner,'create_order',:target,:digest,:version,'prepared')",
                id=command.upstream_operation_id.bytes,
                owner=command.owner_user_id.bytes,
                target=str(command.order_id),
                digest=digest(command),
                version=command.credential_version,
            )
            await execute(
                conn,
                "INSERT INTO adapter_payment_orders (order_id,owner_user_id,binding_id,"
                "upstream_operation_id,credential_ref,credential_version,payload_ciphertext) "
                "VALUES (:id,:owner,:binding,:upstream,:credential,:version,:payload)",
                id=command.order_id.bytes,
                owner=command.owner_user_id.bytes,
                binding=command.binding_id.bytes,
                upstream=command.upstream_operation_id.bytes,
                credential=command.credential_ref.bytes,
                version=command.credential_version,
                payload=self.crypto.seal(payload, aad(command.owner_user_id, command.order_id)),
            )

    async def reserve(self, command, principal):
        await self.proof(command, principal)
        async with self.engine.begin() as conn:
            await self.credential(conn, command)
            row = await first(
                conn,
                "SELECT state FROM upstream_operations WHERE id=:id FOR UPDATE",
                id=command.upstream_operation_id.bytes,
            )
            if not row or row["state"] != "prepared":
                return False
            await execute(
                conn,
                "UPDATE upstream_operations SET state='dispatched',"
                "dispatched_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=command.upstream_operation_id.bytes,
            )
            await record_audit(
                conn,
                "school_adapter",
                "school.order_dispatched",
                "order",
                command.order_id,
                command.request_id,
                actor=command.owner_user_id,
            )
        return True

    async def settle(self, command, *, payload=None, rejected=False, error=None):
        async with self.engine.begin() as conn:
            row = await first(
                conn,
                "SELECT state,dispatched_at FROM upstream_operations WHERE id=:id FOR UPDATE",
                id=command.upstream_operation_id.bytes,
            )
            if row["state"] in {"confirmed", "rejected"}:
                return
            state = (
                "confirmed"
                if payload
                else "rejected"
                if rejected
                else ("unknown" if row["dispatched_at"] else "prepared")
            )
            if payload:
                await execute(
                    conn,
                    "UPDATE adapter_payment_orders SET payload_ciphertext=:payload "
                    "WHERE order_id=:id",
                    id=command.order_id.bytes,
                    payload=self.crypto.seal(payload, aad(command.owner_user_id, command.order_id)),
                )
            await execute(
                conn,
                "UPDATE upstream_operations SET state=:state,error_code=:error,"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                state=state,
                error=error,
                id=command.upstream_operation_id.bytes,
            )

    def payload(self, row):
        return self.crypto.open(
            row["payload_ciphertext"],
            aad(UUID(bytes=row["owner_user_id"]), UUID(bytes=row["order_id"])),
        )
