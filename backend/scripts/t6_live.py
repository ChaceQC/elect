"""指定本人默认寝室的真实验收；未解决订单不能为第二个金额让路。"""

import argparse
import asyncio
import base64
import json
import os
import sys
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from uuid import UUID

from scripts.t2_smoke import browser, fixture_apps
from scripts.t5_live_delivery import authenticate
from services.common.config_contract import SideEffectPolicy
from services.common.dates import today
from services.common.ids import new_id
from services.common.security import Principal
from services.payment.api import CreateCommand
from services.payment.orders import create_order, get_order, order_view, unresolved
from services.payment.policy import validate_amount
from services.payment.reconciliation import check_tick
from services.payment.worker import worker_tick
from services.room.worker import control_tick, sync_tick
from services.school_adapter.infrastructure.ocr import solve_image
from services.school_adapter.infrastructure.payment_ledger import PaymentLedger
from services.school_adapter.infrastructure.payment_sessions import PaymentSessions
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.transport import SchoolTransport


async def binding(client, apps, record):
    response = await client.post(
        "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
    )
    if response.status_code != 202:
        raise RuntimeError("绑定同步未受理")
    for _ in range(30):
        await sync_tick(apps["room"])
        await control_tick(apps["room"])
        data = (await client.get("/api/v1/room-bindings?page_size=100")).json()["data"]
        selected = next(
            (item for item in data["items"] if item["id"] == data["default_binding_id"]), None
        )
        if selected and data["sync_status"] == "ready":
            if (
                selected["status"] != "active"
                or selected["balance"] is None
                or selected["balance"]["amount"] is None
            ):
                raise RuntimeError("默认寝室无有效学校余额")
            record["default_binding_confirmed"] = True
            return selected
    raise RuntimeError("默认寝室未完成确认")


def candidate_amounts(balance):
    amount = Decimal(balance)
    low = amount.to_integral_value(rounding=ROUND_CEILING) - 1
    high = amount.to_integral_value(rounding=ROUND_FLOOR) + 1
    if not low < amount < high:
        raise RuntimeError("金额关系不成立")
    for value in (low, high):
        validate_amount(format(value, ".2f"))
    return {"lower": format(low, ".2f"), "higher": format(high, ".2f")}


async def proof(adapter, owner, order, record):
    ledger = PaymentLedger(adapter)
    row = await ledger.get(owner, order)
    payload = ledger.payload(row)
    record["d01_state"] = row["state"]
    record["d01_dispatch_reserved"] = bool(row["dispatched_at"])
    record["prepay_received"] = bool(payload["prepay_id"])
    record["school_order_id_known"] = payload["sdgl_order_id"] is not None
    observation = row["observation_ciphertext"]
    if observation:
        from services.school_adapter.infrastructure.payment_ledger import aad

        observations = ledger.crypto.open(observation, aad(owner, order, "observation"))
        data = observations.get("D02", {}).get("data")
        record["d02_data_type"] = type(data).__name__
        record["d02_status_candidates"] = {
            key: value
            for key, value in (data.items() if isinstance(data, dict) else [])
            if key in {"payStatus", "status", "orderStatus", "payStatusStr"}
            and type(value) in {str, int}
            and len(str(value)) <= 32
        }
    image = await PaymentSessions(adapter).image(owner, order)
    if image:
        record["qr_received"] = True
        return base64.b64decode(image["image_base64"], validate=True)
    record["qr_received"] = False
    return None


async def verify(args, record):
    apps, _ = await fixture_apps()
    adapter = apps["school_adapter"].state
    protocol = SchoolProtocol(SchoolTransport(adapter.school_store))
    adapter.school_protocol = adapter.school_auth.protocol = adapter.school_sessions.protocol = (
        protocol
    )
    adapter.school_sessions.solver = solve_image
    for app in apps.values():
        app.state.side_effect_policy = SideEffectPolicy()
    try:
        async with browser(apps["gateway"]) as client:
            record["stage"] = "authentication"
            owner = await authenticate(
                client, None, record, (args.credentials["student"], args.credentials["password"])
            )
            record["stage"] = "default_binding_read"
            target = await binding(client, apps, record)
            amounts = candidate_amounts(target["balance"]["amount"])
            record["candidates"] = amounts
            record["amount_policy"] = "application_1_to_500_integer"
            pending = await unresolved(apps["payment"].state.database, owner, UUID(target["id"]))
            record["unresolved_order_present"] = pending is not None
            if args.phase == "readonly":
                record["stage"] = "readonly_completed"
                return
            if pending and args.phase == "create":
                record["stage"] = "blocked_by_existing_order"
                record["order_id"] = str(UUID(bytes=pending["id"]))
                return
            principal = Principal("payment", owner, 1, new_id())
            if args.phase == "create":
                credential = await apps["payment"].state.service_client.call(
                    "school_adapter",
                    "/credentials/control-view",
                    "credential:control-read",
                    principal.request_id,
                    principal=principal,
                )
                command = CreateCommand(
                    binding_id=UUID(target["id"]),
                    amount=amounts[args.relation],
                    idempotency_key=f"t6-live:{owner}:{args.relation}",
                )
                # 专用指定目标验收直接受理；公共 capabilities 仍为 false，不伪造已验收标志。
                accepted = await create_order(
                    apps["payment"].state.database, principal, command, target, credential
                )
                order = accepted.order_id
                record["selected_relation"] = args.relation
                record["selected_amount"] = command.amount
                record["stage"] = "one_d01_dispatch"
                adapter.side_effect_policy = SideEffectPolicy(
                    payment_order_writes=True, payment_form_writes=True
                )
                await worker_tick(apps["payment"], order_id=order)
            else:
                order = UUID(args.order_id)
                existing = await get_order(apps["payment"].state.database, owner, order)
                if existing["binding_id"] != UUID(target["id"]).bytes:
                    raise RuntimeError("指定订单不是本人默认寝室")
            record["order_id"] = str(order)
            record["stage"] = "read_payment_status"
            async with apps["payment"].state.database.begin() as conn:
                from services.common.sql import execute

                await execute(
                    conn,
                    "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) WHERE id=:id",
                    id=order.bytes,
                )
            await check_tick(apps["payment"], order_id=order)
            view = order_view(await get_order(apps["payment"].state.database, owner, order))
            record["order_state"], record["qr_status"] = view.state, view.qr_status
            record["paid_confirmed"] = view.paid_confirmed
            image = await proof(adapter, owner, order, record)
            if image and args.qr_output:
                args.qr_output.write_bytes(image)
                args.qr_output.chmod(0o600)
            record["stage"] = "completed_without_automatic_payment"
            await client.post("/api/v1/auth/logout")
    finally:
        adapter.side_effect_policy = SideEffectPolicy()
        for app in apps.values():
            await app.state.service_client.close()
            if app.state.database:
                await app.state.database.dispose()
        await adapter.redis.aclose()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["readonly", "create", "check"], required=True)
    parser.add_argument("--relation", choices=["lower", "higher"], default="lower")
    parser.add_argument("--order-id")
    parser.add_argument("--qr-output", type=Path)
    args = parser.parse_args()
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise SystemExit("仅允许隔离验收环境")
    args.credentials = json.loads(sys.stdin.read())
    record = {
        "date": str(today()),
        "scope": "本人默认寝室指定金额",
        "real_payment_performed": False,
        "public_payment_enabled": False,
        "stage": "starting",
    }
    code = 0
    try:
        await verify(args, record)
    except Exception as error:
        record["error_code"] = str(getattr(error, "code", type(error).__name__))
        code = 1
    print(json.dumps(record, ensure_ascii=False))
    raise SystemExit(code)


if __name__ == "__main__":
    asyncio.run(main())
