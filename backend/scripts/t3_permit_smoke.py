"""实际数据库发送许可的幂等、过期与取消线性化测试；无 SMTP。"""

import asyncio
from uuid import UUID

from scripts.t3_control_alerts import seed_alerts
from services.common.ids import new_id
from services.common.internal_dto import AuthorizeSend
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.permits import authorize


async def verify_permits(engine, crypto):
    for cancel_first in [False, True]:
        owner = new_id()
        episode = await seed_alerts(engine, crypto, owner, states=("reserved",))
        async with engine.connect() as conn:
            slot = await first(
                conn, "SELECT id FROM alert_slots WHERE episode_id=:id", id=episode.bytes
            )
        command = AuthorizeSend(
            owner_user_id=owner,
            request_id=new_id(),
            alert_slot_id=UUID(bytes=slot["id"]),
            job_id=new_id(),
            generation=1,
            email_version=1,
            execution_epoch=1,
        )
        if cancel_first:
            await MonitorConfiguration(engine, crypto).patch(
                owner, MonitorPatch(expected_version=1, enabled=False), new_id()
            )
            assert not (await authorize(engine, command)).permitted
            continue
        a, b = await asyncio.gather(authorize(engine, command), authorize(engine, command))
        assert a.permitted and a.permit_id == b.permit_id
        different = command.model_copy(update={"execution_epoch": 2})
        assert not (await authorize(engine, different)).permitted
        async with engine.begin() as conn:
            await execute(
                conn,
                "UPDATE send_permits SET expires_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) "
                "WHERE id=:id",
                id=a.permit_id.bytes,
            )
        assert not (await authorize(engine, command)).permitted
        await MonitorConfiguration(engine, crypto).patch(
            owner, MonitorPatch(expected_version=1, enabled=False), new_id()
        )
        assert not (await authorize(engine, command)).permitted
        view = await MonitorConfiguration(engine, crypto).get(owner)
        assert view.notification.in_flight_count == 1
    for change in ["generation", "email", "credential", "sample", "cooldown", "ordinal"]:
        owner = new_id()
        episode = await seed_alerts(engine, crypto, owner, states=("reserved",))
        async with engine.begin() as conn:
            slot = await first(
                conn, "SELECT * FROM alert_slots WHERE episode_id=:id", id=episode.bytes
            )
            if change == "credential":
                await execute(
                    conn,
                    "UPDATE monitors SET credential_allowed=0 WHERE owner_user_id=:owner",
                    owner=owner.bytes,
                )
            elif change == "sample":
                await execute(
                    conn,
                    "UPDATE monitor_samples SET captured_at=DATE_SUB(UTC_TIMESTAMP(6),"
                    "INTERVAL 6 MINUTE) WHERE id=:id",
                    id=slot["sample_id"],
                )
            elif change == "cooldown":
                await execute(
                    conn,
                    "UPDATE monitors SET last_email_sent_at=UTC_TIMESTAMP(6) "
                    "WHERE owner_user_id=:owner",
                    owner=owner.bytes,
                )
            elif change == "ordinal":
                await execute(conn, "UPDATE alert_slots SET ordinal=4 WHERE id=:id", id=slot["id"])
        denied_command = AuthorizeSend(
            owner_user_id=owner,
            request_id=new_id(),
            alert_slot_id=UUID(bytes=slot["id"]),
            job_id=new_id(),
            generation=2 if change == "generation" else 1,
            email_version=2 if change == "email" else 1,
            execution_epoch=1,
        )
        assert not (await authorize(engine, denied_command)).permitted
    owner = new_id()
    episode = await seed_alerts(engine, crypto, owner, states=("reserved",))
    async with engine.connect() as conn:
        slot = await first(
            conn, "SELECT id FROM alert_slots WHERE episode_id=:id", id=episode.bytes
        )
    command = AuthorizeSend(
        owner_user_id=owner,
        request_id=new_id(),
        alert_slot_id=UUID(bytes=slot["id"]),
        job_id=new_id(),
        generation=1,
        email_version=1,
        execution_epoch=1,
    )
    permit, view = await asyncio.gather(
        authorize(engine, command),
        MonitorConfiguration(engine, crypto).patch(
            owner, MonitorPatch(expected_version=1, enabled=False), new_id()
        ),
    )
    assert not view.config.enabled
    assert view.notification.in_flight_count == int(permit.permitted)
    assert not (await authorize(engine, command)).permitted
    print("发送许可并发幂等、不同 epoch/过期不重授、取消前后授权边界：通过（未发信）")
    print("代次/邮箱/凭据/样本新鲜度/冷却/序号检查、并发关闭与授权串行：通过")
