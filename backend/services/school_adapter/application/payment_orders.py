"""学校主路径 D01 一次发送；不启用 D03，不用空 D04 清除未知订单。"""

from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute
from services.payment.policy import validate_amount

from ..infrastructure.payment_ledger import PaymentLedger, aad, digest
from ..infrastructure.payment_protocol import check_pay_url
from ..infrastructure.protocol import API
from ..infrastructure.transport import Deadline, parse_json
from .payment_records import confirm_original, paid_order


class SchoolOrders:
    def __init__(self, state):
        self.state, self.ledger = state, PaymentLedger(state)

    async def dispatch(self, command, principal):
        validate_amount(command.amount)
        intent = await self.ledger.proof(command, principal)
        if any(
            str(intent[key]) != str(getattr(command, key))
            for key in ("binding_id", "credential_ref", "amount", "currency", "credential_version")
        ):
            raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "建单参数与持久订单不同")
        try:
            row = await self.ledger.get(command.owner_user_id, command.order_id)
        except ApiError as error:
            if error.status != 404:
                raise
            target = await self.state.service_client.call(
                "room",
                "/controls/query-target",
                "room:query",
                command.request_id,
                {"binding_id": str(command.binding_id)},
                principal=principal,
            )
            await self.ledger.prepare(
                command,
                {
                    "school_room_id": target["school_room_id"],
                    "amount": command.amount,
                    "pay_url": None,
                    "prepay_id": None,
                    "sdgl_order_id": None,
                },
            )
            row = await self.ledger.get(command.owner_user_id, command.order_id)
        if row["request_digest"] != digest(command):
            raise ApiError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "学校订单请求已变化")
        if row["state"] != "prepared":
            return self.result(row)
        if not self.state.side_effect_policy.payment_order_writes:
            await self.ledger.settle(command, rejected=True, error=ErrorCode.PAYMENT_UNAVAILABLE)
        else:
            await self.send(command, principal, row)
        return self.result(await self.ledger.get(command.owner_user_id, command.order_id))

    async def send(self, command, principal, row):
        payload = self.ledger.payload(row)

        async def send(token, school_user, deadline):
            transport = self.state.school_protocol.transport
            async with transport.client() as client:
                response = await transport.request(
                    client,
                    "POST",
                    f"{API}/base/order/phonePay",
                    deadline,
                    authenticated=True,
                    read_timeout=40,
                    pool="background",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "userId": school_user,
                        "buildId": payload["school_room_id"],
                        "orderType": 0,
                        "payMethod": 1,
                        "orderAmount": int(validate_amount(command.amount)),
                    },
                )
                return parse_json(response, authenticated=True, check_code=False)

        try:
            value = await self.state.school_sessions.write_once(
                command, lambda: self.ledger.reserve(command, principal), send
            )
            if value is None:
                return
            if type(value.get("code")) is int and value["code"] not in {200, 401, 403}:
                await self.ledger.settle(
                    command, rejected=True, error=ErrorCode.PAYMENT_UNAVAILABLE
                )
            elif type(value.get("code")) is int and value["code"] == 200:
                url = value.get("data")
                prepay = check_pay_url(url, accept=True)
                await self.ledger.settle(
                    command, payload={**payload, "pay_url": url, "prepay_id": prepay}
                )
            else:
                await self.ledger.settle(command, error=ErrorCode.SCHOOL_INVALID_RESPONSE)
        except ApiError as error:
            latest = await self.ledger.get(command.owner_user_id, command.order_id)
            await self.ledger.settle(
                command,
                rejected=latest["state"] == "prepared"
                and error.code in {ErrorCode.SCHOOL_REAUTH_REQUIRED, ErrorCode.NOT_FOUND},
                error=error.code,
            )

    @staticmethod
    def result(row):
        return {
            "state": row["state"],
            "error_code": row["error_code"],
            "upstream_operation_id": str(UUID(bytes=row["upstream_operation_id"])),
        }

    async def check(self, owner, order, request_id):
        row = await self.ledger.get(owner, order)
        payload = self.ledger.payload(row)
        if row["state"] == "prepared":
            return self.result(row)
        if row["state"] == "rejected":
            return {**self.result(row), "order_state": "rejected"}
        observations, error = {}, None
        state = "status_unknown" if payload["prepay_id"] else "submit_unknown"
        budget = Deadline(75)

        async def confirm(candidates):
            return await confirm_original(
                self.state, owner, payload, candidates, observations, budget
            )

        try:
            if await paid_order(
                self.state.school_sessions, owner, request_id, row, payload, observations, budget,
                confirm=confirm,
            ):
                state = "paid_confirmed"
        except ApiError as failure:
            error = failure.code
            observations["D04-error"] = {"code": str(failure.code)}
        async with self.ledger.engine.begin() as conn:
            await execute(
                conn,
                "UPDATE adapter_payment_orders SET observation_ciphertext=:value "
                "WHERE order_id=:id",
                id=order.bytes,
                value=self.ledger.crypto.seal(observations, aad(owner, order, "observation")),
            )
        return {**self.result(row), "order_state": state, "error_code": error}
