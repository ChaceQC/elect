"""审查/修复历史别名；默认只读，每批独立提交，不调用学校或迁移。"""

import argparse
import asyncio
import json
from collections import Counter
from uuid import UUID

from services.common.database import create_database
from services.common.dates import windows
from services.common.runtime import load_runtime
from services.common.sql import execute, first

from .history_links import OPEN, root_operation
from .preference_store import lock_preference


async def classify(conn, alias):
    sync = await first(conn, "SELECT * FROM history_syncs WHERE operation_id=:root",
                       root=alias["upstream_operation_id"])
    if not sync:
        return "orphan_or_chain", None
    root = await root_operation(conn, sync["id"])
    own = await first(conn, "SELECT id FROM history_syncs WHERE operation_id=:id", id=alias["id"])
    if (not root or own or alias["id"] == root["id"]
            or any(alias[key] != root[key] for key in
                   ("owner_user_id", "target_binding_id", "target_room_id"))):
        return "relation_conflict", None
    rows = (await execute(conn, "SELECT start_date,end_date,state,error_code FROM "
                          "history_sync_windows WHERE sync_id=:id ORDER BY start_date",
                          id=sync["id"])).mappings().all()
    if [(r["start_date"], r["end_date"]) for r in rows] != list(
            windows(sync["requested_start"], sync["requested_end"])):
        return "window_conflict", None
    if root["state"] in {"accepted", "running"} or any(
            r["state"] in {"pending", "running", "retry_wait"} for r in rows):
        return "waiting", None
    expected = "failed" if any(r["state"] == "failed" for r in rows) else "succeeded"
    errors = {r["error_code"] for r in rows if r["state"] == "failed"}
    if (any(r["state"] not in {"succeeded", "failed"} for r in rows)
            or sync["status"] != expected or root["state"] != expected
            or sync["error_code"] != root["error_code"]
            or (expected == "succeeded" and root["error_code"] is not None)
            or (expected == "failed" and root["error_code"] not in errors)):
        return "terminal_conflict", None
    return "repairable", root


async def repair_batch(engine, *, apply=False, after=bytes(16), batch_size=100):
    if not 1 <= batch_size <= 100:
        raise ValueError("每批必须为1..100条")
    result = Counter()
    async with engine.begin() as conn:
        rows = (await execute(conn, "SELECT id,owner_user_id FROM room_operations "
                              "WHERE id>:after AND type='history_sync' AND state IN " + OPEN
                              + " AND upstream_operation_id IS NOT NULL ORDER BY id LIMIT :n",
                              after=after, n=batch_size)).mappings().all()
        for item in rows:
            if apply:
                await lock_preference(conn, UUID(bytes=item["owner_user_id"]))
            alias = await first(conn, "SELECT * FROM room_operations WHERE id=:id "
                                "AND state IN " + OPEN + (" FOR UPDATE" if apply else ""),
                                id=item["id"])
            result["candidates"] += 1
            if not alias:
                result["already_terminal"] += 1
                continue
            category, root = await classify(conn, alias)
            result[category] += 1
            if apply and root:
                await execute(conn, "UPDATE room_operations SET state=:state,error_code=:error,"
                              "saga_step='complete',next_reconcile_at=NULL,"
                              "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                              id=alias["id"], state=root["state"], error=root["error_code"])
                result["applied"] += 1
    # 游标仅用于断点续扫，不含账号、请求正文、幂等摘要或任何凭据。
    summary = {key: result[key] for key in ("candidates", "repairable", "waiting", "applied")}
    summary["conflicts"] = sum(result[key] for key in
                               ("orphan_or_chain", "relation_conflict", "window_conflict",
                                "terminal_conflict"))
    return {"counts": dict(result), "summary": summary,
            "after": rows[-1]["id"].hex() if rows else after.hex(),
            "exhausted": len(rows) < batch_size}


async def run(args):
    runtime = load_runtime("room")
    engine = create_database(runtime.db_url.get_secret_value())
    try:
        cursor = UUID(args.after).bytes
        for _ in range(args.batches):
            report = await repair_batch(engine, apply=args.apply, after=cursor,
                                        batch_size=args.batch_size)
            print(json.dumps({"mode": "apply" if args.apply else "dry-run", **report}))
            cursor = bytes.fromhex(report["after"])
            if report["exhausted"]:
                break
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--after", default=str(UUID(int=0)), type=UUID)
    parser.add_argument("--batch-size", default=100, type=int, choices=range(1, 101))
    parser.add_argument("--batches", default=1, type=int, choices=range(1, 101))
    args = parser.parse_args()
    args.after = str(args.after)
    try:
        asyncio.run(run(args))
    except Exception:
        # 配置、驱动和SQL异常可能含URL/参数；不输出异常原文。
        raise SystemExit("修复未完成；本批回滚。请检查环境并从上次已提交游标重试。") from None


if __name__ == "__main__":
    main()
