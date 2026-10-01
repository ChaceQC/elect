"""只读核对指定原订单和本人默认寝室；复用加密凭据，不重新建单。"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from scripts.t2_smoke import fixture_apps
from services.common.config_contract import SideEffectPolicy
from services.common.dates import today
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first
from services.payment.orders import order_view
from services.payment.reconciliation import check_tick
from services.room.repository import RoomRepository
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.transport import SchoolTransport


class ObservedTransport(SchoolTransport):
    def __init__(self, store, record):
        super().__init__(store)
        self.record = record

    async def request(self, *args, **kwargs):
        response = await super().request(*args, **kwargs)
        if response.url.path.endswith("getPayOrderReturnUrl"):
            self.record["d02_http_status"] = response.status_code
            try:
                value = response.json()
                self.record["d02_business_code"] = value.get("code")
                data = value.get("data")
                self.record["d02_data_type"] = type(data).__name__
                self.record["d02_status_candidates"] = {
                    key: item for key, item in (data.items() if isinstance(data, dict) else [])
                    if key in {"payStatus", "status", "orderStatus", "payStatusStr"}
                    and type(item) in {str, int} and len(str(item)) <= 32
                }
            except (ValueError, AttributeError):
                self.record["d02_data_type"] = "unrecognized"
        return response


async def verify(order, record):
    apps, _ = await fixture_apps()
    adapter = apps["school_adapter"].state
    protocol = SchoolProtocol(ObservedTransport(adapter.school_store, record))
    adapter.school_protocol = adapter.school_auth.protocol = adapter.school_sessions.protocol = (
        protocol
    )
    for app in apps.values():
        app.state.side_effect_policy = SideEffectPolicy()
    try:
        async with apps["payment"].state.database.connect() as conn:
            row = await first(conn, "SELECT * FROM payment_orders WHERE id=:id", id=order.bytes)
        if not row or row["amount"] != Decimal("1.00"):
            raise RuntimeError("仅核对本轮指定1元原订单")
        owner = UUID(bytes=row["owner_user_id"])
        binding = UUID(bytes=row["binding_id"])
        before = await RoomRepository(apps["room"].state.database).list(owner, "", 1, 100)
        if before.default_binding_id != binding:
            raise RuntimeError("指定订单不属于本人当前默认寝室")
        cached = next(item.balance for item in before.items if item.id == binding)
        async with apps["payment"].state.database.begin() as conn:
            await execute(
                conn, "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=order.bytes,
            )
        await check_tick(apps["payment"], order_id=order)
        async with apps["payment"].state.database.connect() as conn:
            result = await first(conn, "SELECT * FROM payment_orders WHERE id=:id", id=order.bytes)
        view = order_view(result)
        record.update(order_state=view.state, paid_confirmed=view.paid_confirmed,
                      order_error_code=view.error_code)
        principal = Principal("payment", owner, 1, new_id())
        target = await apps["payment"].state.service_client.call(
            "room", "/controls/query-target", "room:query", principal.request_id,
            {"binding_id": str(binding)}, principal=principal,
        )
        observed = await apps["room"].state.service_client.call(
            "school_adapter", "/rooms/bound", "school:rooms", principal.request_id,
            principal=principal,
        )
        matching = [item for item in observed["items"]
                    if item["room_id"] == target["school_room_id"]]
        if len(matching) != 1 or matching[0]["balance"] is None:
            raise RuntimeError("指定寝室未取得可匹配的学校余额")
        amount = matching[0]["balance"]
        record["fresh_b02_same_room"] = True
        record["balance_increased_by_one_yuan"] = bool(
            cached and cached.amount is not None and Decimal(amount) - Decimal(cached.amount) == 1
        )
        await adapter.service_client.call(
            "room", "/controls/balance-observed", "room:balance-commit", principal.request_id,
            {"binding_id": str(binding), "amount": amount,
             "fetched_at": datetime.now(UTC).isoformat()}, principal=principal,
        )
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=UUID, required=True)
    args = parser.parse_args()
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise SystemExit("仅限指定隔离验收环境")
    record = {"date": str(today()), "order_id": str(args.order_id),
              "scope": "指定1元原订单只读核对", "public_payment_enabled": False}
    try:
        await verify(args.order_id, record)
    except Exception as error:
        record["error_code"] = str(getattr(error, "code", type(error).__name__))
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
