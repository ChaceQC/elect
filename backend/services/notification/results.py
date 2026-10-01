"""投递终态与 Outbox 同事务；回报失败不重放 SMTP。"""

from datetime import timedelta
from uuid import UUID

from services.common.audit_events import record_audit
from services.common.events import DeliveryReportedPayload
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.outbox import append_event
from services.common.sql import aware, execute, first

from .repository import locked_execution

RETRY_DELAYS = (60, 300, 900)


async def settle(conn, row, outcome, request_id, *, recovering=False):
    state, error = outcome.state, outcome.error_code
    if state == "retry_wait" and row["attempt_count"] >= 4:
        state = "failed"
    clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
    delay = RETRY_DELAYS[max(0, row["attempt_count"] - 1)] if 1 <= row["attempt_count"] <= 3 else 30
    retry = clock["now"] + timedelta(seconds=delay) if state == "retry_wait" else None
    version = row["version"] + 1
    await execute(
        conn,
        "UPDATE notification_jobs SET state=:state,version=:version,reported_version=:version,"
        "execution_epoch=execution_epoch+:recovering,next_attempt_at=:retry,last_error_code=:error,"
        "lease_owner=NULL,lease_until=NULL,updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
        id=row["id"],
        state=state,
        version=version,
        retry=retry,
        error=error,
        recovering=int(recovering),
    )
    attempt_state = {
        "sent": "accepted",
        "retry_wait": "retryable",
        "failed": "rejected",
        "delivery_unknown": "unknown",
        "cancelled": "cancelled",
    }[state]
    await execute(
        conn,
        "UPDATE notification_attempts SET state=:state,provider_result=:error,"
        "finished_at=UTC_TIMESTAMP(6) WHERE job_id=:id AND attempt_no=:attempt AND state='started'",
        id=row["id"],
        attempt=row["attempt_count"],
        state=attempt_state,
        error=error,
    )
    await append_event(
        conn,
        EventEnvelope(
            event_id=new_id(),
            type="notification.delivery_reported",
            schema_version=1,
            producer="notification",
            aggregate_id=UUID(bytes=row["id"]),
            aggregate_version=version,
            occurred_at=aware(clock["now"]),
            request_id=request_id,
            payload=DeliveryReportedPayload(
                job_id=UUID(bytes=row["id"]),
                alert_slot_id=UUID(bytes=row["alert_slot_id"]),
                execution_epoch=row["execution_epoch"],
                state=state,
                error_code=error,
                next_retry_at=aware(retry),
            ),
            dedupe_key=f"{UUID(bytes=row['id'])}/{version}",
        ),
    )
    await record_audit(
        conn,
        "notification",
        "notification.delivery_reported",
        "notification_job",
        UUID(bytes=row["id"]),
        request_id,
        actor=None,
        version=version,
        result="succeeded"
        if state == "sent"
        else "unknown"
        if state == "delivery_unknown"
        else "cancelled"
        if state == "cancelled"
        else "failed",
    )


async def finish(engine, job, outcome, request_id):
    async with engine.begin() as conn:
        row = await locked_execution(conn, job)
        if not row:
            return False
        await settle(conn, row, outcome, request_id)
    return True
