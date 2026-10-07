"""过期快照连续小批回收；owner游标轮转，分页共享锁优先。"""

import asyncio
import time
from dataclasses import dataclass

from services.common.logging import log
from services.common.sql import execute, first

SNAPSHOT_BATCH = 4
MEMBER_BATCH = 1_000
ROUND_BATCHES = 10
ROUND_SECONDS = 0.5


@dataclass
class CleanupBatch:
    candidates: int = 0
    members: int = 0
    parents: int = 0
    skipped_locks: int = 0
    observed_members: int = 0
    oldest_age_seconds: int = 0


class SnapshotCleaner:
    def __init__(self):
        self.after_owner = b""
        self.pressure_pauses = 0

    async def batch(self, engine):
        report = CleanupBatch()
        async with engine.begin() as conn:
            candidates = (await execute(
                conn, "SELECT id,owner_user_id,total,"
                "TIMESTAMPDIFF(SECOND,expires_at,UTC_TIMESTAMP(6)) AS age "
                "FROM sample_snapshots WHERE owner_user_id>:after "
                "AND expires_at<=UTC_TIMESTAMP(6) ORDER BY owner_user_id,expires_at,id LIMIT 64",
                after=self.after_owner,
            )).mappings().all()
            if not candidates:
                self.after_owner = b""
                return report
            selected = {}
            for row in candidates:
                selected.setdefault(row["owner_user_id"], row)
                if len(selected) >= SNAPSHOT_BATCH:
                    break
            self.after_owner = list(selected)[-1]
            report.candidates = len(selected)
            for candidate in selected.values():
                row = await first(
                    conn, "SELECT id,total FROM sample_snapshots WHERE id=:id "
                    "AND expires_at<=UTC_TIMESTAMP(6) FOR UPDATE SKIP LOCKED", id=candidate["id"],
                )
                if not row:
                    report.skipped_locks += 1
                    continue
                report.observed_members += row["total"]
                report.oldest_age_seconds = max(report.oldest_age_seconds, candidate["age"])
                result = await execute(
                    conn, "DELETE FROM sample_snapshot_items WHERE snapshot_id=:id "
                    "ORDER BY position LIMIT :limit", id=row["id"],
                    limit=MEMBER_BATCH // len(selected),
                )
                report.members += result.rowcount
                remaining = await first(conn, "SELECT position FROM sample_snapshot_items "
                                        "WHERE snapshot_id=:id LIMIT 1", id=row["id"])
                if not remaining:
                    await execute(conn, "DELETE FROM sample_snapshots WHERE id=:id", id=row["id"])
                    report.parents += 1
        return report

    async def round(self, engine, stop):
        started, backlog, batches = time.monotonic(), False, 0
        while batches < ROUND_BATCHES and not stop.is_set():
            if time.monotonic() - started >= ROUND_SECONDS:
                break
            if engine.pool.checkedout() >= engine.pool.size():
                self.pressure_pauses += 1
                log("snapshot_pressure_pause", service="monitoring", count=self.pressure_pauses)
                return 15
            before = time.monotonic()
            cursor = self.after_owner
            report = await self.batch(engine)
            batches += 1
            log("snapshot_cleanup_batch", service="monitoring", count=report.members,
                duration_ms=round((time.monotonic() - before) * 1000))
            for name in ("parents", "skipped_locks", "observed_members", "oldest_age_seconds"):
                log(f"snapshot_cleanup_{name}", service="monitoring", count=getattr(report, name))
            if not report.candidates:
                if not cursor:
                    backlog = False
                    break
            else:
                backlog = True
            await asyncio.sleep(0)
        return 1 if backlog or batches >= ROUND_BATCHES else 60


async def cleanup_snapshots(engine):
    """单批兼容入口；后台使用同一个轮转实例。"""
    report = await SnapshotCleaner().batch(engine)
    return report.candidates > report.skipped_locks
