"""单次运行的本人读取与取消，不改变后续计划。"""

from uuid import UUID

from services.common.archive_store import unpack
from services.common.audit_events import record_audit
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import aware, execute, first

from .dto import Run
from .repository import lock_monitor, require_version


async def run_view(conn, row):
    if not row:
        return None
    attempts = (
        (
            await execute(
                conn,
                "SELECT * FROM monitor_attempts WHERE run_id=:id ORDER BY attempt_no",
                id=row["id"],
            )
        )
        .mappings()
        .all()
    )
    archived = (await execute(conn, "SELECT * FROM archive_records WHERE kind='monitor_attempts' "
        "AND object_key LIKE :prefix ORDER BY object_key", prefix=row["id"].hex() + ":%"
    )).mappings().all()
    combined = {item["id"]: item for item in attempts}
    for record in archived:
        item = unpack(record)
        if item["run_id"] != row["id"]:
            from services.common.archive_store import unavailable

            raise unavailable()
        combined[item["id"]] = item
    attempts = sorted(combined.values(), key=lambda item: item["attempt_no"])
    return Run(
        id=UUID(bytes=row["id"]),
        version=row["version"],
        binding_id=UUID(bytes=row["binding_id"]),
        state=row["state"],
        scheduled_for=aware(row["scheduled_for"]),
        started_at=aware(row["started_at"]),
        finished_at=aware(row["finished_at"]),
        next_attempt_at=aware(row["next_attempt_at"]),
        cancel_pending=row["state"] == "cancel_requested",
        error_code=row["error_code"],
        attempts=[
            {
                "attempt_no": item["attempt_no"],
                "started_at": aware(item["started_at"]),
                "finished_at": aware(item["finished_at"]),
                "outcome": item["outcome"],
                "error_code": item["error_code"],
            }
            for item in attempts
        ],
    )


async def cancel_run(engine, owner, run_id, expected, request_id):
    async with engine.begin() as conn:
        monitor = await lock_monitor(conn, owner)
        row = await first(
            conn,
            "SELECT * FROM monitor_runs WHERE id=:id AND monitor_id=:monitor FOR UPDATE",
            id=run_id.bytes,
            monitor=monitor["id"],
        )
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "运行不存在")
        require_version(row["version"], expected)
        if row["state"] in {"pending", "retry_wait", "running"}:
            state = "cancel_requested" if row["state"] == "running" else "cancelled"
            await execute(
                conn,
                "UPDATE monitor_runs SET state=:state,execution_epoch=execution_epoch+1,"
                "version=version+1,cancel_requested_at=UTC_TIMESTAMP(6),next_attempt_at=NULL,"
                "finished_at=IF(:state='cancelled',UTC_TIMESTAMP(6),finished_at),"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                state=state,
                id=row["id"],
            )
            if state == "cancelled":
                await execute(
                    conn,
                    "UPDATE monitors SET active_run_id=NULL WHERE id=:id AND active_run_id=:run",
                    id=monitor["id"],
                    run=row["id"],
                )
            await record_audit(
                conn,
                "monitoring",
                "monitor.run_cancelled",
                "run",
                run_id,
                request_id,
                actor=owner,
                version=row["version"] + 1,
            )
        # 已成功的运行保持成功，只取消由该样本产生且尚未授权的提醒。
        slots = await execute(
            conn,
            "UPDATE alert_slots s JOIN monitor_samples p ON p.id=s.sample_id "
            "SET s.state='cancelled',s.finished_at=UTC_TIMESTAMP(6) "
            "WHERE p.run_id=:run AND s.state='reserved'",
            run=run_id.bytes,
        )
        if slots.rowcount:
            await record_audit(
                conn,
                "monitoring",
                "monitor.run_alerts_cancelled",
                "run",
                run_id,
                request_id,
                actor=owner,
                version=row["version"],
            )
        row = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=run_id.bytes)
        return await run_view(conn, row)
