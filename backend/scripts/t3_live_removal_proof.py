"""真实删除后检查台账/缺席时间/本域保留与默认一致，只输出分类事实。"""

import argparse
import asyncio
import json
import os
from uuid import UUID

from services.common.database import create_database
from services.common.runtime import Runtime, read_secret
from services.common.sql import first


async def verify(operation):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅用于显式隔离验收")
    engines = {}
    for domain in ["room", "school_adapter", "monitoring"]:
        runtime = Runtime.model_validate_json(read_secret(f"/run/secrets/{domain}_runtime.json"))
        engines[domain] = create_database(runtime.db_url.get_secret_value())
    try:
        async with engines["room"].connect() as conn:
            row = await first(
                conn,
                "SELECT o.*,b.status AS binding_state,c.binding_id AS cached_id,r.school_room_id "
                "FROM room_operations o JOIN room_bindings b ON b.id=o.target_binding_id "
                "JOIN rooms r ON r.id=b.room_id LEFT JOIN room_balance_cache c "
                "ON c.binding_id=b.id "
                "WHERE o.id=:id AND o.type='unbind_room'",
                id=operation.bytes,
            )
            assert row and row["state"] == "succeeded" and row["binding_status"] == "removed"
            assert row["binding_state"] == "inactive" and row["cached_id"]
            preference = await first(
                conn,
                "SELECT * FROM room_preferences WHERE owner_user_id=:owner",
                owner=row["owner_user_id"],
            )
            assert preference["removal_operation_id"] is None
        async with engines["school_adapter"].connect() as conn:
            upstream = await first(
                conn,
                "SELECT *,TIMESTAMPDIFF(SECOND,absence_first_at,updated_at) AS absence_seconds "
                "FROM upstream_operations WHERE id=:id AND owner_user_id=:owner",
                id=row["upstream_operation_id"],
                owner=row["owner_user_id"],
            )
            assert upstream and upstream["state"] == "confirmed" and upstream["dispatched_at"]
            assert (
                upstream["target_ref"] == row["school_room_id"]
                and upstream["candidate_ciphertext"] is None
            )
            assert upstream["absence_seconds"] >= 2
            record = json.loads(upstream["confirmed_record"])
            assert record["building"] == "枫苑5号" and record["number"] == "402"
            count = await first(
                conn,
                "SELECT COUNT(*) AS n FROM outbox_events WHERE aggregate_id=:id "
                "AND type='audit.recorded' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.payload.action'))"
                "='school.unbinding_dispatched'",
                id=upstream["id"],
            )
            assert count["n"] == 1
        async with engines["monitoring"].connect() as conn:
            monitor = await first(
                conn,
                "SELECT binding_id,desired_enabled FROM monitors WHERE owner_user_id=:owner",
                owner=row["owner_user_id"],
            )
            assert monitor["binding_id"] == preference["default_binding_id"]
        return {
            "upstream_remove_dispatch_count": count["n"],
            "B02_repeated_absence_confirmed": True,
            "absence_confirmation_seconds": upstream["absence_seconds"],
            "binding_archived": True,
            "history_cache_retained": True,
            "monitor_default_consistent": True,
            "monitor_enabled": bool(monitor["desired_enabled"]),
            "ledger_proof": "passed",
        }
    finally:
        for engine in engines.values():
            await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation-id", type=UUID, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(verify(args.operation_id))
    except Exception as error:
        raise SystemExit(
            f"真实解绑台账核验失败（{type(error).__name__}），未输出敏感材料"
        ) from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
