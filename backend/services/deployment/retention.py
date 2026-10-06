"""单领域维护：默认dry-run，限批次、可停止续跑，不触发任何外部业务。"""

import argparse
import asyncio
import json
import os
import signal
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from services.common.archive_store import unpack
from services.common.domains import DATABASES
from services.common.retention import archive_transport
from services.common.sql import execute
from services.migrate_all_mysql import migration_urls

KINDS = {
    "room": {"room_operations"},
    "monitoring": {"monitor_run_requests", "monitor_attempts"},
    "payment": {"payment_qr_requests"},
    "identity": {"temporary"},
    "school_adapter": {"temporary"},
}


async def batch(engine, domain, kind, cutoff, *, apply=False, limit=200, after=""):
    if not 1 <= limit <= 200:
        raise ValueError("每批上限为200")
    if kind == "temporary" and kind in KINDS.get(domain, set()):
        module = import_module(f"services.{domain}.retention")
        return await module.cleanup(engine, apply=apply, limit=limit, cutoff=cutoff)
    async with engine.begin() as conn:
        if kind == "verify":
            rows = (await execute(conn, "SELECT * FROM archive_records WHERE id>:after "
                "ORDER BY id LIMIT :limit", after=bytes.fromhex(after),
                limit=limit)).mappings().all()
            for row in rows:
                unpack(row)
            return {"verified": len(rows), "candidates": len(rows),
                    "cursor": rows[-1]["id"].hex() if rows else after}
        if kind in {"outbox_events", "inbox_events"}:
            return await archive_transport(conn, kind, cutoff, apply=apply,
                                           limit=limit, after=after)
        if kind in KINDS.get(domain, set()):
            return await import_module(f"services.{domain}.retention").archive(
                conn, kind, cutoff, apply=apply, limit=limit, after=after)
        raise ValueError("本领域归档类别未登记")


def checkpoint(path, identity, after=None):
    if path is None:
        return ""
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("断点必须为非符号链接绝对路径")
    if after is None:
        if not path.exists():
            return ""
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["identity"] != identity:
            raise ValueError("断点目标或模式不匹配")
        return document["after"]
    # 只写受控断点，不含归档原文；事务已提交后写入，丢失时从旧断点幂等重跑。
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump({"identity": identity, "after": after}, output)
    return after


async def run(args):
    stop = asyncio.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stop.set())
    cutoff = datetime.fromisoformat(args.cutoff)
    if cutoff.tzinfo is None:
        raise ValueError("截止时间必须带时区")
    identity = [args.domain, args.kind, args.cutoff, args.apply]
    after = checkpoint(args.checkpoint, identity)
    engine = create_async_engine(migration_urls()[args.domain], pool_size=1, max_overflow=0,
                                 hide_parameters=True, isolation_level="READ COMMITTED")
    totals = {}
    try:
        if args.kind == "capacity":
            from .retention_capacity import sample

            totals = await sample(engine, args.capacity_limit_mib, args.baseline,
                                  domain=args.domain)
            return {"domain": args.domain, "kind": args.kind, "counts": totals}
        for _ in range(args.batches):
            if stop.is_set():
                break
            result = await batch(engine, args.domain, args.kind,
                cutoff.astimezone(UTC).replace(tzinfo=None), apply=args.apply,
                limit=args.limit, after=after)
            for key, value in result.items():
                if type(value) is int:
                    totals[key] = totals.get(key, 0) + value
            after = result.get("cursor", after)
            checkpoint(args.checkpoint, identity, after)
            if not result.get("candidates") or not args.apply and args.kind == "temporary":
                break
            await asyncio.sleep(0)
    finally:
        await engine.dispose()
    return {"domain": args.domain, "kind": args.kind,
            "mode": "apply" if args.apply else "dry-run", "counts": totals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=list(DATABASES), required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, choices=range(1, 201), default=200)
    parser.add_argument("--batches", type=int, choices=range(1, 101), default=1)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--capacity-limit-mib", type=int)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
        document = json.dumps(result)
        if args.report:
            if not args.report.is_absolute() or args.report.is_symlink():
                raise ValueError("报告必须是受控绝对路径")
            fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(document)
        print(document)
    except Exception:
        raise SystemExit("保留维护失败：检查目标、迁移、断点或归档完整性；"
                         "未提交批次已回滚") from None
    if result["counts"].get("over_budget"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
