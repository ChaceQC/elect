"""修复旧paid+failed调度；默认dry-run，只读关联operation，绝不发起新刷新或学校写。"""

import argparse
import asyncio
import json
from collections import Counter
from types import SimpleNamespace
from uuid import UUID

from services.common.database import create_database
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.runtime import load_runtime
from services.common.security import Principal
from services.common.service_client import ServiceClient
from services.common.sql import execute, first

from .reconciliation import refresh_status


async def repair_batch(state, *, apply=False, after=bytes(16), batch_size=50):
    if not 1 <= batch_size <= 100:
        raise ValueError("每批必须为1..100条")
    async with state.database.connect() as conn:
        rows = (await execute(
            conn, "SELECT * FROM payment_orders WHERE id>:after AND state='paid_confirmed' "
            "AND balance_refresh_state='failed' AND next_check_at IS NOT NULL "
            "ORDER BY id LIMIT :n", after=after, n=batch_size,
        )).mappings().all()
    counts = Counter(candidates=len(rows))
    for row in rows:
        principal = Principal("payment", UUID(bytes=row["owner_user_id"]), 1, new_id())
        try:
            async with asyncio.timeout(10):
                result = await refresh_status(state, row["balance_refresh_operation_id"], principal)
        except (ApiError, TimeoutError):
            counts["unconfirmed"] += 1
            continue
        counts[result] += 1
        if not apply:
            continue
        async with state.database.begin() as conn:
            await execute(conn, "SELECT id FROM payment_operations WHERE order_id=:id FOR UPDATE",
                          id=row["id"])
            current = await first(conn, "SELECT * FROM payment_orders WHERE id=:id FOR UPDATE",
                                  id=row["id"])
            now = (await first(conn, "SELECT UTC_TIMESTAMP(6) AS now"))["now"]
            if (current["state"] != "paid_confirmed" or current["version"] != row["version"]
                    or current["balance_refresh_state"] != "failed"
                    or current["next_check_at"] is None
                    or (current["check_lease_until"] and current["check_lease_until"] > now)):
                counts["changed_or_leased"] += 1
                continue
            await execute(
                conn, "UPDATE payment_orders SET balance_refresh_state=:state,"
                "next_check_at=IF(:state='pending',UTC_TIMESTAMP(6),NULL),"
                "check_lease_owner=NULL,check_lease_until=NULL,version=version+1 WHERE id=:id",
                id=row["id"], state=result,
            )
            counts["applied"] += 1
    return {"counts": dict(counts), "after": rows[-1]["id"].hex() if rows else after.hex(),
            "exhausted": len(rows) < batch_size}


async def run(args):
    runtime = load_runtime("payment")
    state = SimpleNamespace(database=create_database(runtime.db_url.get_secret_value()),
                            service_client=ServiceClient(runtime))
    try:
        cursor = args.after.bytes
        for _ in range(args.batches):
            report = await repair_batch(state, apply=args.apply, after=cursor,
                                        batch_size=args.batch_size)
            print(json.dumps({"mode": "apply" if args.apply else "dry-run", **report}))
            cursor = bytes.fromhex(report["after"])
            if report["exhausted"]:
                break
    finally:
        await state.service_client.close()
        await state.database.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--after", default=UUID(int=0), type=UUID)
    parser.add_argument("--batch-size", default=50, type=int, choices=range(1, 101))
    parser.add_argument("--batches", default=1, type=int, choices=range(1, 101))
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception:
        raise SystemExit("修复未完成，请从上次已提交游标重试；未输出配置或异常原文。") from None


if __name__ == "__main__":
    main()
