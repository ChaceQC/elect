"""prepared 可以继续首次发送；dispatched 以后永远只做安全 B02 回查。"""

from datetime import UTC, datetime

from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.binding_ledger import BindingLedger, aad, result
from ..infrastructure.rooms import bound_rooms
from .binding_candidates import candidate


class BindingWrites:
    def __init__(self, state):
        self.state = state
        self.ledger = BindingLedger(state.database, state.school_credentials.crypto)

    async def query(self, owner, operation, request_id):
        row = await self.ledger.get(owner, operation)
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "上游操作不存在")
        if row["state"] in {"confirmed", "rejected"}:
            return result(row)
        try:
            value = await self.state.school_sessions.read(
                owner, request_id, "/base/roomUser/selectRoomListByUserId", {}, include_user=True
            )
            record = next(
                (item for item in bound_rooms(value) if item["room_id"] == row["target_ref"]), None
            )
            return await self.ledger.settle(owner, operation, request_id, record=record)
        except ApiError as error:
            return await self.ledger.settle(owner, operation, request_id, error=error.code)

    async def dispatch(self, command):
        owner, operation = command.owner_user_id, command.upstream_operation_id
        row = self.ledger.replay(await self.ledger.get(owner, operation), command)
        if row is None:
            value = await candidate(self.state, owner, command.candidate_id)
            row = await self.ledger.prepare(command, value)
        if row["state"] != "prepared":
            return await self.query(owner, operation, command.request_id)
        before = await self.query(owner, operation, command.request_id)
        if before["state"] != "prepared" or before["error_code"]:
            return before
        value = self.ledger.crypto.open(row["candidate_ciphertext"], aad(owner, operation))
        if datetime.fromisoformat(value["expires_at"]) <= datetime.now(UTC):
            return await self.ledger.settle(
                owner, operation, command.request_id, rejected=ErrorCode.ROOM_CANDIDATE_EXPIRED
            )
        if not self.state.side_effect_policy.school_binding_writes:
            return await self.ledger.settle(
                owner, operation, command.request_id, rejected=ErrorCode.FEATURE_DISABLED
            )
        try:
            response = await self.state.school_sessions.bind_once(
                command, value["record"], lambda: self.ledger.reserve(command)
            )
            if response is not None:
                code = response.get("code")
                if type(code) is int and code not in {200, 401, 403}:
                    return await self.ledger.settle(
                        owner,
                        operation,
                        command.request_id,
                        rejected=ErrorCode.SCHOOL_BINDING_REJECTED,
                    )
                if type(code) is not int or code != 200:
                    return await self.ledger.settle(
                        owner,
                        operation,
                        command.request_id,
                        error=ErrorCode.SCHOOL_INVALID_RESPONSE,
                    )
        except ApiError as error:
            # 发送前的明确凭据变化可以终结；已 dispatched 的任何异常保持回查。
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
