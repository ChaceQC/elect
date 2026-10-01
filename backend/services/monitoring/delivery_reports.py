"""投递进度镜像：monitor 锁、job 版本与许可 epoch 阻止迟到回报。"""

from datetime import UTC

from services.common.sql import execute, first

from .alerts import refresh_counts


async def apply_report(conn, event):
    report = event.payload
    if event.aggregate_id != report.job_id:
        raise ValueError("投递聚合与 job 不匹配")
    target = await first(
        conn,
        "SELECT e.monitor_id FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
        "WHERE s.id=:id",
        id=report.alert_slot_id.bytes,
    )
    if not target:
        raise ValueError("投递 slot 不存在")
    monitor = await first(
        conn, "SELECT * FROM monitors WHERE id=:id FOR UPDATE", id=target["monitor_id"]
    )
    slot = await first(
        conn, "SELECT * FROM alert_slots WHERE id=:id FOR UPDATE", id=report.alert_slot_id.bytes
    )
    if (
        slot["delivery_id"]
        and slot["delivery_id"] != report.job_id.bytes
        or event.aggregate_version <= slot["delivery_version"]
    ):
        return
    permit = await first(
        conn,
        "SELECT * FROM send_permits WHERE job_id=:id AND execution_epoch=:epoch",
        id=report.job_id.bytes,
        epoch=report.execution_epoch,
    )
    if report.state in {"sent", "delivery_unknown"} and (
        not permit or permit["alert_slot_id"] != slot["id"] or slot["permit_id"] != permit["id"]
    ):
        raise ValueError("可能发送的回报缺少对应许可")
    if slot["state"] == "authorized" and (not permit or slot["permit_id"] != permit["id"]):
        return
    if slot["state"] in {"sent", "delivery_unknown", "failed"}:
        return
    state = report.state
    if state == "retry_wait":
        state = (
            "reserved"
            if (
                slot["state"] != "cancelled"
                and monitor["state"] == "active"
                and monitor["desired_enabled"]
                and slot["generation"] == monitor["generation"]
                and slot["email_version"] == monitor["email_version"]
            and slot["episode_id"] == monitor["current_episode_id"]
            )
            else "cancelled"
        )
    next_retry = (
        report.next_retry_at.astimezone(UTC).replace(tzinfo=None) if report.next_retry_at else None
    )
    await execute(
        conn,
        "UPDATE alert_slots SET state=:state,delivery_id=:job,delivery_version=:version,"
        "last_error_code=:error,next_retry_at=:retry,send_lease_until=NULL,"
        "permit_id=IF(:reserved,NULL,permit_id),finished_at=IF(:reserved,NULL,UTC_TIMESTAMP(6)),"
        "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
        id=slot["id"],
        state=state,
        job=report.job_id.bytes,
        version=event.aggregate_version,
        error=report.error_code,
        retry=next_retry if state == "reserved" else None,
        reserved=state == "reserved",
    )
    if state == "sent":
        await execute(
            conn,
            "UPDATE monitors SET last_email_sent_at=GREATEST(COALESCE(last_email_sent_at,"
            ":at),:at) WHERE id=:id",
            id=monitor["id"],
            at=event.occurred_at.astimezone(UTC).replace(tzinfo=None),
        )
    await refresh_counts(conn, monitor["id"])
