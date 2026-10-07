"""邮件提示重建与投递回报；所有状态仍由本域 MySQL 决定。"""

from services.common.broker import verified_event
from services.common.ids import new_id
from services.common.logging import log
from services.common.outbox import consume_once
from services.common.sql import execute

from .alerts import refresh_counts, wake_alert
from .delivery_reports import apply_report


async def wake_tick(engine):
    async with engine.begin() as conn:
        monitors = (
            (
                await execute(
                    conn,
                    "SELECT * FROM monitors WHERE id IN (SELECT e.monitor_id FROM alert_episodes e "
                    "JOIN alert_slots s ON s.episode_id=e.id WHERE s.state='reserved' "
                    "AND (s.wake_at IS NULL OR s.wake_at<="
                    "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 15 SECOND))) "
                    "ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED",
                )
            )
            .mappings()
            .all()
        )
        for monitor in monitors:
            slots = (
                (
                    await execute(
                        conn,
                        "SELECT s.* FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
                        "WHERE e.monitor_id=:id AND s.state='reserved' "
                        "AND (s.wake_at IS NULL OR s.wake_at<="
                        "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 15 SECOND))",
                        id=monitor["id"],
                    )
                )
                .mappings()
                .all()
            )
            for slot in slots:
                sample = (
                    await execute(
                        conn,
                        "SELECT id FROM monitor_samples WHERE id=:id "
                        "AND captured_at>=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 5 MINUTE)",
                        id=slot["sample_id"],
                    )
                ).first()
                if (
                    not sample
                    or slot["sample_id"] != monitor["last_sample_id"]
                    or slot["generation"] != monitor["generation"]
                ):
                    await execute(
                        conn,
                        "UPDATE alert_slots SET state='cancelled',next_retry_at=NULL,"
                        "finished_at=UTC_TIMESTAMP(6) WHERE id=:id",
                        id=slot["id"],
                    )
                else:
                    await wake_alert(conn, monitor, slot, new_id())
            await refresh_counts(conn, monitor["id"])
    return bool(monitors)


async def report_tick(app, queue):
    from services.common.transport_health import receive

    message = await receive(queue)
    if message is None:
        return False
    try:
        event = verified_event(app.state.runtime, message)
        if event.type != "notification.delivery_reported" or event.producer != "notification":
            raise ValueError("错误投递回报")
    except Exception:
        await message.reject(requeue=False)
        log("delivery_report_rejected", service="monitoring", error_code="INVALID_EVENT")
        return True
    try:
        await consume_once(
            app.state.database, "notification.delivery_reported", event, apply_report
        )
    except ValueError:
        await message.reject(requeue=False)
        log("delivery_report_rejected", service="monitoring", error_code="INVALID_DELIVERY")
        return True
    except Exception:
        await message.nack(requeue=True)
        raise
    await message.ack()
    return True
