"""T5 必要投递边界的短验收：真实 MySQL + 本机模拟 SMTP。"""

import asyncio
import os
from uuid import UUID

from scripts.t5_alert_smoke import collect
from scripts.t5_fixtures import SmtpSimulator, close_apps, make_job, owner_with_monitor, setup
from services.common.internal_dto import EventEnvelope
from services.common.outbox import consume_once
from services.common.sql import execute, first
from services.monitoring.delivery_reports import apply_report
from services.notification.consumer import consume_alert
from services.notification.recovery import recovery_tick
from services.notification.repository import claim
from services.notification.worker import execute_job, worker_tick


async def reports(apps):
    async with apps["notification"].state.database.connect() as conn:
        rows = (
            (
                await execute(
                    conn,
                    "SELECT payload FROM outbox_events WHERE "
                    "type='notification.delivery_reported' ORDER BY event_id",
                )
            )
            .scalars()
            .all()
        )
    for raw in rows:
        event = (
            EventEnvelope.model_validate_json(raw)
            if isinstance(raw, str)
            else EventEnvelope.model_validate(raw)
        )
        await consume_once(
            apps["monitoring"].state.database, "notification.delivery_reported", event, apply_report
        )


async def job_state(app, job_id):
    async with app.state.database.connect() as conn:
        return await first(conn, "SELECT * FROM notification_jobs WHERE id=:id", id=job_id)


async def verify(apps):
    monitor, notification = apps["monitoring"], apps["notification"]
    for mode, expected in [
        ("accepted", "sent"),
        ("disconnect", "delivery_unknown"),
        ("permanent", "failed"),
        ("temporary", "retry_wait"),
    ]:
        owner = await owner_with_monitor(apps)
        sample = await collect(monitor.state.database, owner, "19.99")
        job, event = await make_job(apps, sample)
        assert not await consume_alert(notification, event)
        a, b = await asyncio.gather(
            claim(notification.state.database, UUID(bytes=job["id"])),
            claim(notification.state.database, UUID(bytes=job["id"])),
        )
        assert bool(a) != bool(b)
        async with SmtpSimulator(mode) as smtp:
            notification.state.smtp = smtp.transport
            assert await execute_job(notification, a or b)
            await reports(apps)
            current = await job_state(notification, job["id"])
            assert current["state"] == expected
            if mode == "temporary":
                async with notification.state.database.begin() as conn:
                    await execute(
                        conn,
                        "UPDATE notification_jobs SET next_attempt_at=UTC_TIMESTAMP(6) "
                        "WHERE id=:id",
                        id=job["id"],
                    )
                assert await worker_tick(notification, UUID(bytes=job["id"]))
                await reports(apps)
                current = await job_state(notification, job["id"])
                assert current["state"] == "sent" and current["attempt_count"] == 2
                assert current["message_id"] == job["message_id"]
            else:
                assert not await worker_tick(notification, UUID(bytes=job["id"]))
            summary = await monitor_summary(monitor, owner)
            if mode == "disconnect":
                assert summary.notification.delivery_unknown_count == 1
            elif mode == "permanent":
                assert summary.notification.state == "email_failed"
            else:
                assert summary.notification.state == "sent" and summary.notification.last_sent_at
            assert len(smtp.messages) == int(mode != "permanent")
            if smtp.messages:
                assert b"https://elect.test.local/monitor" in smtp.messages[0]
        print(f"SMTP {mode}、job/Inbox去重、多Worker互斥、状态镜像：通过")
    owner = await owner_with_monitor(apps)
    job, _ = await make_job(apps, await collect(monitor.state.database, owner, "19.00"))
    from services.common.ids import new_id
    from services.monitoring.configuration import MonitorConfiguration
    from services.monitoring.dto import MonitorPatch

    config = MonitorConfiguration(monitor.state.database, monitor.state.email_crypto)
    saved = await config.get(owner)
    await config.patch(owner, MonitorPatch(expected_version=saved.version, enabled=False), new_id())
    async with SmtpSimulator() as smtp:
        notification.state.smtp = smtp.transport
        await worker_tick(notification, UUID(bytes=job["id"]))
        assert smtp.connections == 0
    assert (await job_state(notification, job["id"]))["state"] == "cancelled"
    await reports(apps)
    # DATA 后进程丢失通过持久边界恢复，不再连接 SMTP。
    owner = await owner_with_monitor(apps)
    job, _ = await make_job(apps, await collect(monitor.state.database, owner, "18.00"))
    claimed = await claim(notification.state.database, UUID(bytes=job["id"]))
    from services.common.internal_dto import AuthorizeSend
    from services.monitoring.permits import authorize
    from services.notification.repository import mark_body, record_permit

    permit = await authorize(
        monitor.state.database,
        AuthorizeSend(
            owner_user_id=owner,
            request_id=new_id(),
            alert_slot_id=UUID(bytes=job["alert_slot_id"]),
            job_id=UUID(bytes=job["id"]),
            generation=job["generation"],
            email_version=job["email_version"],
            execution_epoch=claimed["execution_epoch"],
        ),
    )
    assert permit.permitted
    await record_permit(notification.state.database, claimed, permit)
    await mark_body(notification.state.database, claimed)
    async with notification.state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE notification_jobs SET lease_until=UTC_TIMESTAMP(6) WHERE id=:id",
            id=job["id"],
        )
    assert await recovery_tick(notification.state.database)
    await reports(apps)
    assert (await job_state(notification, job["id"]))["state"] == "delivery_unknown"
    print("发送前取消零连接、正文边界后租约恢复保留unknown/不重发：通过")


async def monitor_summary(app, owner):
    from services.monitoring.configuration import MonitorConfiguration

    return await MonitorConfiguration(app.state.database, app.state.email_crypto).get(owner)


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("只允许隔离测试环境")
    apps = await setup()
    try:
        await verify(apps)
    finally:
        await close_apps(apps)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T5投递验收失败（{type(error).__name__}）") from None
