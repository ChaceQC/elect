"""控制变更对合成提醒的边界；不创建 Notification job 或发送邮件。"""

from scripts.t3_control_fixtures import running, write_sample
from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch


async def seed_alerts(engine, crypto, owner):
    execution, _ = await running(engine, owner)
    episode = new_id()
    async with engine.begin() as conn:
        await write_sample(conn, execution, owner)
        sample = await first(
            conn, "SELECT id FROM monitor_samples WHERE run_id=:run", run=execution.run_id.bytes
        )
        await execute(
            conn,
            "UPDATE monitor_runs SET state='succeeded' WHERE id=:id",
            id=execution.run_id.bytes,
        )
        await execute(
            conn,
            "INSERT INTO alert_episodes (id,monitor_id,binding_id,generation,opened_at,"
            "state,threshold,recovery_threshold,sent_count,reserved_count) VALUES "
            "(:id,:monitor,:binding,1,UTC_TIMESTAMP(6),'open',20,21,1,2)",
            id=episode.bytes,
            monitor=execution.monitor_id.bytes,
            binding=execution.binding_id.bytes,
        )
        for ordinal, state in enumerate(["reserved", "authorized", "sent"], 1):
            await execute(
                conn,
                "INSERT INTO alert_slots (id,episode_id,ordinal,sample_id,generation,"
                "email_version,state,send_lease_until) VALUES (:id,:episode,:ordinal,:sample,1,1,"
                ":state,IF(:state='authorized',"
                "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND),NULL))",
                id=new_id().bytes,
                episode=episode.bytes,
                ordinal=ordinal,
                sample=sample["id"],
                state=state,
            )
        await execute(
            conn,
            "UPDATE monitors SET current_episode_id=:episode,repeat_limit=3,"
            "email_ciphertext=:email WHERE id=:id",
            episode=episode.bytes,
            email=crypto.seal("synthetic@example.invalid", owner, 1),
            id=execution.monitor_id.bytes,
        )
    return episode


async def verify_alert_boundary(engine, crypto):
    for changes in [{"enabled": False}, {"threshold": "21.00"}, {"interval_minutes": 75}]:
        owner = new_id()
        episode = await seed_alerts(engine, crypto, owner)
        view = await MonitorConfiguration(engine, crypto).patch(
            owner, MonitorPatch(expected_version=1, **changes), new_id()
        )
        assert view.cancel_pending and view.in_flight_count == 1
        assert view.notification.in_flight_count == 1 and view.notification.state == "sending"
        async with engine.connect() as conn:
            rows = (
                (
                    await execute(
                        conn,
                        "SELECT state FROM alert_slots WHERE episode_id=:id ORDER BY ordinal",
                        id=episode.bytes,
                    )
                )
                .scalars()
                .all()
            )
            current = await first(
                conn, "SELECT * FROM alert_episodes WHERE id=:id", id=episode.bytes
            )
        assert rows == ["cancelled", "authorized", "sent"]
        assert current["sent_count"] == 1
        assert current["state"] == ("open" if "interval_minutes" in changes else "closed")
    print("配置变更取消未授权提醒，保留已授权在途事实；仅改间隔保留事件计数：通过")
