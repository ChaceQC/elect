"""指定原订单的学校只读验收；推进本地余额刷新，输出分类证据。"""

import argparse
import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from scripts.t2_smoke import fixture_apps
from services.common.config_contract import SideEffectPolicy
from services.common.dates import today
from services.common.ids import new_id
from services.common.internal_dto import BindingQuery
from services.common.security import Principal
from services.common.sql import aware, first
from services.payment.reconciliation import check_tick
from services.room.query_worker import query_tick
from services.school_adapter.application.payment_records import confirms_paid, created_for_attempt
from services.school_adapter.infrastructure.payment_ledger import PaymentLedger, aad
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.transport import SchoolTransport
from services.school_adapter.query_api import collect


async def verify(apps, order_id, record):
    adapter = apps["school_adapter"].state
    adapter.school_sessions.protocol = SchoolProtocol(SchoolTransport(adapter.school_store))
    for app in apps.values():
        app.state.side_effect_policy = SideEffectPolicy()
    await query_tick(apps["room"])
    await check_tick(apps["payment"], order_id=order_id)
    async with apps["payment"].state.database.connect() as conn:
        order = await first(conn, "SELECT * FROM payment_orders WHERE id=:id", id=order_id.bytes)
    if not order or order["amount"] != Decimal("1.00"):
        raise ValueError("仅核对指定1元原订单")
    owner, binding = UUID(bytes=order["owner_user_id"]), UUID(bytes=order["binding_id"])
    ledger = PaymentLedger(adapter)
    row = await ledger.get(owner, order_id)
    payload = ledger.payload(row)
    observations = ledger.crypto.open(
        row["observation_ciphertext"], aad(owner, order_id, "observation"))
    record.update(local_state=order["state"], balance_refresh_state=order["balance_refresh_state"],
                  original_ticket_paid=observations.get("original_payment_page", {})
                  .get("paid_confirmed"))
    response = await adapter.school_sessions.read(
        owner, new_id(), "/base/order/page",
        {"buildId": payload["school_room_id"],
         "startTimeStr": aware(order["created_at"]).astimezone(ZoneInfo("Asia/Shanghai"))
         .date().isoformat(), "endTimeStr": today().isoformat(), "current": 1,
         "size": 10, "pageTotal": 100, "orderType": 0, "payMethod": 1, "payStatus": 2},
        read_timeout=20,
    )
    credential = await adapter.school_credentials.current(owner)
    school_user = adapter.school_credentials.payload(credential)["school_user_id"]
    candidates = [item for item in response["data"]["records"]
                  if confirms_paid(item, payload) and item.get("userId") == str(school_user)
                  and created_for_attempt(item, order["created_at"])]
    record["matching_paid_records"] = len(candidates)
    if len(candidates) == 1:
        item = candidates[0]
        record.update(same_user=True, same_room=True, amount="1.00", school_pay_status="2",
                      paid_at=item["payTime"], balance_increment_one_yuan=(
                          Decimal(item["afterAmount"]) - Decimal(item["beforeAmount"]) == 1))
    result = await collect(
        BindingQuery(binding_id=binding), SimpleNamespace(app=apps["school_adapter"]),
        Principal("monitoring", owner, 1, new_id()),
    )
    meter = result.get("meter")
    record.update(fresh_balance_received=True, meter_readings_present=bool(meter),
                  meter_record_date=meter["record_date"] if meter else None,
                  meter_quality=meter["quality"] if meter else "balance_only")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=UUID, required=True)
    args = parser.parse_args()
    apps, _ = await fixture_apps()
    record = {"date": str(today()), "order_id": str(args.order_id), "external_writes": False}
    try:
        await verify(apps, args.order_id, record)
    except Exception as error:
        record["error_code"] = str(getattr(error, "code", type(error).__name__))
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if app.state.database:
                await app.state.database.dispose()
        await apps["school_adapter"].state.redis.aclose()
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
