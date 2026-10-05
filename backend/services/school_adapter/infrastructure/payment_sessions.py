"""支付会话及表单阶段权威；响应持久化与推进阶段在同一事务中完成。"""

import base64
import hashlib
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first

from .payment_ledger import PaymentLedger, aad


class PaymentSessions:
    def __init__(self, state):
        self.ledger = PaymentLedger(state)
        self.engine, self.crypto = self.ledger.engine, self.ledger.crypto

    async def get(self, owner, order):
        async with self.engine.connect() as conn:
            return await first(
                conn,
                "SELECT * FROM payment_sessions WHERE order_id=:id AND owner_user_id=:owner",
                id=order.bytes,
                owner=owner.bytes,
            )

    async def claim(self, owner, order):
        lease = str(new_id())
        async with self.engine.begin() as conn:
            await execute(
                conn,
                "INSERT INTO payment_sessions (order_id,owner_user_id,version,state) "
                "VALUES (:id,:owner,1,'created') ON DUPLICATE KEY UPDATE order_id=order_id",
                id=order.bytes,
                owner=owner.bytes,
            )
            result = await execute(
                conn,
                "UPDATE payment_sessions SET lease_owner=:lease,"
                "lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 SECOND) WHERE order_id=:id "
                "AND owner_user_id=:owner AND (lease_until IS NULL OR "
                "lease_until<=UTC_TIMESTAMP(6))",
                id=order.bytes,
                owner=owner.bytes,
                lease=lease,
            )
        return lease if result.rowcount else None

    def payload(self, row):
        owner, order = UUID(bytes=row["owner_user_id"]), UUID(bytes=row["order_id"])
        return (
            self.crypto.open(row["hidden_fields_ciphertext"], aad(owner, order, "fields"))
            if row["hidden_fields_ciphertext"]
            else {}
        )

    def cookies(self, row):
        owner, order = UUID(bytes=row["owner_user_id"]), UUID(bytes=row["order_id"])
        return (
            self.crypto.open(row["cookiejar_ciphertext"], aad(owner, order, "cookies"))
            if row["cookiejar_ciphertext"]
            else []
        )

    @staticmethod
    def step_id(order, step):
        return uuid5(NAMESPACE_URL, f"elect-payment:{order}:{step}")

    async def reserve_form(self, command, principal, order_row, lease, step):
        await self.ledger.proof(command, principal)
        operation = self.step_id(command.order_id, step)
        credential = SimpleNamespace(
            owner_user_id=command.owner_user_id,
            credential_ref=UUID(bytes=order_row["credential_ref"]),
            credential_version=order_row["credential_version"],
        )
        async with self.engine.begin() as conn:
            await self.ledger.credential(conn, credential)
            row = await self.lock(conn, command, lease)
            prior = await first(
                conn,
                "SELECT state FROM upstream_operations WHERE id=:id FOR UPDATE",
                id=operation.bytes,
            )
            if prior or row["flow_step"] != step or row["state"] == "unknown":
                return False
            await execute(
                conn,
                "INSERT INTO upstream_operations (id,owner_user_id,operation_type,"
                "target_ref,request_digest,credential_version,state,dispatched_at) "
                "VALUES (:id,:owner,:step,:target,:digest,:version,'dispatched',UTC_TIMESTAMP(6))",
                id=operation.bytes,
                owner=command.owner_user_id.bytes,
                step=step,
                target=str(command.order_id),
                digest=hashlib.sha256(f"{command.order_id}:{step}".encode()).digest(),
                version=credential.credential_version,
            )
            await record_audit(
                conn,
                "school_adapter",
                f"school.payment_{step.lower()}_dispatched",
                "order",
                command.order_id,
                command.request_id,
                actor=command.owner_user_id,
            )
        return True

    async def lock(self, conn, command, lease):
        row = await first(
            conn,
            "SELECT * FROM payment_sessions WHERE order_id=:id AND "
            "owner_user_id=:owner AND lease_owner=:lease AND "
            "lease_until>UTC_TIMESTAMP(6) FOR UPDATE",
            id=command.order_id.bytes,
            owner=command.owner_user_id.bytes,
            lease=lease,
        )
        if not row:
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "支付页面执行租约已变化")
        return row

    async def save(self, command, lease, step, payload, cookies, *, image=None):
        next_step = {"E01": "E02", "E02": "E03", "E03": "E04", "E04": "ready"}[step]
        async with self.engine.begin() as conn:
            await self.lock(conn, command, lease)
            await execute(
                conn,
                "UPDATE payment_sessions SET state='active',flow_step=:step,"
                "hidden_fields_ciphertext=:fields,cookiejar_ciphertext=:cookies,version=version+1,"
                "qr_ciphertext=:qr,qr_mime=:mime,updated_at=UTC_TIMESTAMP(6) WHERE order_id=:id",
                id=command.order_id.bytes,
                step=next_step,
                fields=self.crypto.seal(
                    payload, aad(command.owner_user_id, command.order_id, "fields")
                ),
                cookies=self.crypto.seal(
                    cookies, aad(command.owner_user_id, command.order_id, "cookies")
                ),
                qr=self.crypto.seal(
                    base64.b64encode(image[0]).decode(),
                    aad(command.owner_user_id, command.order_id, "qr"),
                )
                if image
                else None,
                mime=image[1] if image else None,
            )
            if step in {"E02", "E03"}:
                await execute(
                    conn,
                    "UPDATE upstream_operations SET state='confirmed',updated_at=UTC_TIMESTAMP(6) "
                    "WHERE id=:id",
                    id=self.step_id(command.order_id, step).bytes,
                )

    async def failed(self, command, lease):
        async with self.engine.begin() as conn:
            row = await self.lock(conn, command, lease)
            prior = await first(
                conn,
                "SELECT state FROM upstream_operations WHERE id=:id",
                id=self.step_id(command.order_id, row["flow_step"]).bytes,
            )
            if prior and prior["state"] == "dispatched":
                await execute(
                    conn,
                    "UPDATE payment_sessions SET state='unknown' WHERE order_id=:id",
                    id=command.order_id.bytes,
                )
                await execute(
                    conn,
                    "UPDATE upstream_operations SET state='unknown' WHERE id=:id",
                    id=self.step_id(command.order_id, row["flow_step"]).bytes,
                )
                return "unknown"
            return "failed"

    async def release(self, order, lease):
        async with self.engine.begin() as conn:
            await execute(
                conn,
                "UPDATE payment_sessions SET lease_owner=NULL,lease_until=NULL "
                "WHERE order_id=:id AND lease_owner=:lease",
                id=order.bytes,
                lease=lease,
            )

    async def image(self, owner, order):
        row = await self.get(owner, order)
        if not row or not row["qr_ciphertext"]:
            return None
        value = self.crypto.open(row["qr_ciphertext"], aad(owner, order, "qr"))
        return {"image_base64": value, "mime": row["qr_mime"]}
