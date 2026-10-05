"""按持久阶段继续 E01–E04，未知 E02/E03 永远不重新提交。"""

from urllib.parse import urljoin, urlsplit

from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.payment_ledger import PaymentLedger
from ..infrastructure.payment_protocol import form_fields, hidden_fields, image_bytes, qr_url
from ..infrastructure.payment_sessions import PaymentSessions
from ..infrastructure.payment_transport import PaymentTransport
from ..infrastructure.protocol import dump_cookies
from ..infrastructure.transport import Deadline


class PaymentFlow:
    def __init__(self, state):
        self.state, self.ledger, self.sessions = state, PaymentLedger(state), PaymentSessions(state)
        self.transport = getattr(state, "payment_transport", None) or PaymentTransport(
            state.school_store
        )

    async def run(self, command, principal):
        order = await self.ledger.get(command.owner_user_id, command.order_id)
        if order["state"] != "confirmed":
            return {"qr_status": "unknown", "error_code": "ORDER_NOT_CONFIRMED"}
        await self.ledger.proof(command, principal)
        lease = await self.sessions.claim(command.owner_user_id, command.order_id)
        if not lease:
            return {"qr_status": "generating", "error_code": None}
        try:
            return await self.advance(command, principal, order, lease)
        except ApiError as error:
            status = await self.sessions.failed(command, lease)
            return {"qr_status": status, "error_code": error.code}
        finally:
            await self.sessions.release(command.order_id, lease)

    async def advance(self, command, principal, order, lease):
        deadline = Deadline(70)
        row = await self.sessions.get(command.owner_user_id, command.order_id)
        if row["state"] == "unknown":
            return {"qr_status": "unknown", "error_code": "PAYMENT_FORM_UNKNOWN"}
        if command.step == "E04" and row["flow_step"] == "ready":
            from services.common.sql import execute

            async with self.sessions.engine.begin() as conn:
                await self.sessions.lock(conn, command, lease)
                await execute(
                    conn,
                    "UPDATE payment_sessions SET flow_step='E04' WHERE order_id=:id",
                    id=command.order_id.bytes,
                )
            row = await self.sessions.get(command.owner_user_id, command.order_id)
        payload = self.ledger.payload(order)
        url = payload["pay_url"]
        origin = urlsplit(url).hostname
        async with self.transport.client() as client:
            for cookie in self.sessions.cookies(row):
                if cookie["domain"].lstrip(".") != origin:
                    raise ApiError(
                        502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "支付 Cookie 范围不受支持"
                    )
                client.cookies.set(
                    cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"]
                )
            while row["flow_step"] != "ready":
                step, fields = row["flow_step"], self.sessions.payload(row)
                if step == "E01":
                    response = await self.transport.request(client, "GET", url, deadline)
                    fields = {"hidden": hidden_fields(response.text), "referer": str(response.url)}
                elif step in {"E02", "E03"}:
                    if not self.state.side_effect_policy.payment_form_writes:
                        raise ApiError(403, ErrorCode.PAYMENT_UNAVAILABLE, "学校支付表单暂未开放")
                    if not await self.sessions.reserve_form(command, principal, order, lease, step):
                        # 上次 dispatch 后崩溃也走此分支；绝不从 E01 重建并重发。
                        return {"qr_status": "unknown", "error_code": "PAYMENT_FORM_UNKNOWN"}
                    main = urljoin(url, "PayMain.aspx?prePayId=" + payload["prepay_id"])
                    response = await self.transport.request(
                        client,
                        "POST",
                        main,
                        deadline,
                        data=form_fields(fields["hidden"], step),
                        headers={
                            "Referer": fields["referer"],
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        },
                    )
                    fields = (
                        {"hidden": hidden_fields(response.text), "referer": str(response.url)}
                        if step == "E02"
                        else {"qr_url": qr_url(response.text, str(response.url))}
                    )
                else:
                    response = await self.transport.request(
                        client, "GET", fields["qr_url"], deadline
                    )
                picture = image_bytes(response.content) if step == "E04" else None
                await self.sessions.save(
                    command, lease, step, fields, dump_cookies(client), image=picture
                )
                row = await self.sessions.get(command.owner_user_id, command.order_id)
        return {"qr_status": "ready", "error_code": None}
