"""单次解绑与两次 B02 缺席确认，unknown 不重新发送。"""

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first

from ..infrastructure.binding_ledger import BindingLedger, aad, result
from ..infrastructure.rooms import bound_rooms
from .removal_checks import require_intent


class RemovalWrites:
    def __init__(self, state):
        self.state = state
        self.ledger = BindingLedger(state.database, state.school_credentials.crypto, "unbind_room")

    async def observe(self, owner, operation, present):
        async with self.state.database.begin() as conn:
            row = await first(
                conn,
                "SELECT *,absence_first_at<=DATE_SUB(UTC_TIMESTAMP(6),"
                "INTERVAL 30 SECOND) AS repeated_absence FROM upstream_operations "
                "WHERE id=:id AND owner_user_id=:owner FOR UPDATE",
                id=operation.bytes,
                owner=owner.bytes,
            )
            if row["state"] in {"confirmed", "rejected"}:
                return False
            if present:
                await execute(
                    conn,
                    "UPDATE upstream_operations SET absence_first_at=NULL WHERE id=:id",
                    id=operation.bytes,
                )
                return False
            await execute(
                conn,
                "UPDATE upstream_operations SET absence_first_at=COALESCE(absence_first_at,"
                "UTC_TIMESTAMP(6)) WHERE id=:id",
                id=operation.bytes,
            )
            return bool(row["repeated_absence"])

    async def query(self, owner, operation, request_id):
        row = await self.ledger.get(owner, operation)
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "学校解绑操作不存在")
        if row["state"] in {"confirmed", "rejected"}:
            return result(row)
        stored = self.ledger.crypto.open(row["candidate_ciphertext"], aad(owner, operation))
        try:
            value = await self.state.school_sessions.read(
                owner, request_id, "/base/roomUser/selectRoomListByUserId", {}, include_user=True
            )
            found = next(
                (item for item in bound_rooms(value) if item["room_id"] == row["target_ref"]), None
            )
            repeated = await self.observe(owner, operation, found is not None)
            if (
                found
                and stored["record"]["relation_id"]
                and found["relation_id"] != stored["record"]["relation_id"]
            ):
                return await self.ledger.settle(
                    owner,
                    operation,
                    request_id,
                    rejected=ErrorCode.VERSION_CONFLICT if row["state"] == "prepared" else None,
                    error=ErrorCode.VERSION_CONFLICT,
                )
            if repeated:
                return await self.ledger.settle(
                    owner, operation, request_id, record=stored["record"]
                )
            return await self.ledger.settle(owner, operation, request_id)
        except ApiError as error:
            await self.observe(owner, operation, True)  # 读取失败不能作为连续缺席证据。
            return await self.ledger.settle(owner, operation, request_id, error=error.code)

    async def dispatch(self, command, principal):
        owner, operation = command.owner_user_id, command.upstream_operation_id
        row = self.ledger.replay(await self.ledger.get(owner, operation), command)
        if row is None:
            proof = await require_intent(self.state, principal, command)
            row = await self.ledger.prepare(
                command, {"record": proof.record.model_dump(mode="json")}
            )
        if row["state"] != "prepared":
            return await self.query(owner, operation, command.request_id)
        before = await self.query(owner, operation, command.request_id)
        if before["state"] != "prepared" or before["error_code"]:
            return before
        stored = self.ledger.crypto.open(row["candidate_ciphertext"], aad(owner, operation))
        # 若当前目标缺席，先等待下一次成功确认，不根据旧 bruId 盲发。
        latest = await self.ledger.get(owner, operation)
        if latest["absence_first_at"]:
            return before
        relation = stored["record"]["relation_id"]
        if not relation:
            return await self.ledger.settle(
                owner, operation, command.request_id, rejected=ErrorCode.SCHOOL_INVALID_RESPONSE
            )
        if not self.state.side_effect_policy.school_binding_writes:
            return await self.ledger.settle(
                owner, operation, command.request_id, rejected=ErrorCode.FEATURE_DISABLED
            )

        async def reserve():
            await require_intent(self.state, principal, command)
            return await self.ledger.reserve(command)

        try:
            response = await self.state.school_sessions.remove_once(command, relation, reserve)
            if (
                response is not None
                and type(response.get("code")) is int
                and response["code"] not in {200, 401, 403}
            ):
                return await self.ledger.settle(
                    owner, operation, command.request_id, rejected=ErrorCode.SCHOOL_BINDING_REJECTED
                )
        except ApiError as error:
            latest = await self.ledger.get(owner, operation)
            return await self.ledger.settle(
                owner,
                operation,
                command.request_id,
                rejected=error.code
                if latest["state"] == "prepared" and error.code == ErrorCode.SCHOOL_REAUTH_REQUIRED
                else None,
                error=error.code,
            )
        return await self.query(owner, operation, command.request_id)
