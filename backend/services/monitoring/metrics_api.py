"""受服务身份保护的持久调度/租约/错误指标，不输出用户或学校信息。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.security import Principal, require_principal
from services.common.sql import execute, first

router = APIRouter(prefix="/internal/v1/monitor")


@router.get("/metrics")
async def metrics(
    request: Request, principal: Annotated[Principal, Depends(require_principal("foundation:read"))]
):
    async with request.app.state.database.connect() as conn:
        plans = await first(
            conn,
            "SELECT COUNT(*) AS active_plans,COALESCE(MAX(GREATEST(0,"
            "TIMESTAMPDIFF(SECOND,next_run_at,UTC_TIMESTAMP(6)))),0) AS "
            "schedule_lag_seconds FROM monitors WHERE state='active' AND "
            "desired_enabled=1",
        )
        runs = (
            (await execute(conn, "SELECT state,COUNT(*) AS n FROM monitor_runs GROUP BY state"))
            .mappings()
            .all()
        )
        leases = await first(
            conn,
            "SELECT COUNT(*) AS expired_leases FROM monitor_runs WHERE state IN "
            "('running','cancel_requested') AND lease_until<=UTC_TIMESTAMP(6)",
        )
        attempts = (
            (
                await execute(
                    conn, "SELECT outcome,COUNT(*) AS n FROM monitor_attempts GROUP BY outcome"
                )
            )
            .mappings()
            .all()
        )
        backlog = await first(
            conn,
            "SELECT COUNT(*) AS ready_runs,COALESCE(MAX(TIMESTAMPDIFF(SECOND,"
            "next_attempt_at,UTC_TIMESTAMP(6))),0) AS oldest_ready_seconds FROM "
            "monitor_runs WHERE state IN ('pending','retry_wait') AND "
            "next_attempt_at<=UTC_TIMESTAMP(6)",
        )
        outbox = await first(
            conn,
            "SELECT COUNT(*) AS unpublished_wakeups FROM outbox_events WHERE "
            "type='monitor.run_ready' AND published_at IS NULL",
        )
        alerts = (await execute(
            conn, "SELECT state,COUNT(*) AS n FROM alert_slots GROUP BY state"
        )).mappings().all()
        faults = await first(conn, "SELECT COUNT(*) AS open_collection_faults FROM "
                             "monitor_fault_episodes WHERE closed_at IS NULL")
    return {
        **plans,
        **leases,
        **backlog,
        **outbox,
        **faults,
        "alert_slots": {s["state"]: s["n"] for s in alerts},
        "runs": {r["state"]: r["n"] for r in runs},
        "attempts": {r["outcome"]: r["n"] for r in attempts},
    }
