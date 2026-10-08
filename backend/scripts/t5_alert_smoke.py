"""隔离 MySQL 内的事件/序号/周期故障验收，不发送 SMTP。"""

import asyncio
import os
from uuid import UUID

from scripts.fixture_time import next_request_minute
from scripts.t2_smoke import fixture_apps
from scripts.t3_control_fixtures import running
from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.alerts import on_sample, refresh_counts
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.execution import claim_run
from services.monitoring.results import fail, succeed
from services.monitoring.scheduler import accept_run


async def collect(engine, owner, amount):
    run = await accept_run(engine, owner, str(new_id()), new_id())
    execution = await claim_run(engine, UUID(bytes=run["id"]))
    assert execution
    return await succeed(engine, execution, amount, new_id())


async def slots(engine, owner):
    async with engine.connect() as conn:
        return (
            (
                await execute(
                    conn,
                    "SELECT s.* FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
                    "JOIN monitors m ON m.id=e.monitor_id "
                    "WHERE m.owner_user_id=:owner ORDER BY s.id",
                    owner=owner.bytes,
                )
            )
            .mappings()
            .all()
        )


async def accepted(engine, slot, *, unknown=False):
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE alert_slots SET state=:state,authorized_at=DATE_SUB(UTC_TIMESTAMP(6),"
            "INTERVAL 61 MINUTE) WHERE id=:id",
            id=slot["id"],
            state="delivery_unknown" if unknown else "sent",
        )
        episode = await first(
            conn, "SELECT monitor_id FROM alert_episodes WHERE id=:id", id=slot["episode_id"]
        )
        await refresh_counts(conn, episode["monitor_id"])


async def verify(app):
    engine, owner = app.state.database, new_id()
    await running(engine, owner)
    config = MonitorConfiguration(engine, app.state.email_crypto)
    view = await config.patch(
        owner,
        MonitorPatch(expected_version=1, email="synthetic@example.invalid", repeat_limit=3),
        new_id(),
    )
    await collect(engine, owner, "20.00")
    assert not await slots(engine, owner)
    sample = await collect(engine, owner, "19.99")
    rows = await slots(engine, owner)
    assert len(rows) == 1 and rows[0]["ordinal"] == 1
    async with engine.begin() as conn:
        monitor = await first(
            conn, "SELECT * FROM monitors WHERE owner_user_id=:id FOR UPDATE", id=owner.bytes
        )
        await on_sample(conn, monitor, sample, new_id())
    assert len(await slots(engine, owner)) == 1
    await accepted(engine, rows[0])
    await collect(engine, owner, "20.50")
    assert len(await slots(engine, owner)) == 1
    await collect(engine, owner, "-0.01")
    rows = await slots(engine, owner)
    assert rows[-1]["ordinal"] == 2 and rows[-1]["episode_id"] == rows[0]["episode_id"]
    await accepted(engine, rows[-1], unknown=True)
    # 仅改次数/间隔不清零，旧未授权序号可释放。
    view = await config.patch(
        owner,
        MonitorPatch(expected_version=view.version, repeat_limit=2, interval_minutes=75),
        new_id(),
    )
    await collect(engine, owner, "10.00")
    assert len(await slots(engine, owner)) == 2
    # 配置触发的立即采集也占用户额度；后续事件周期推进到下一分钟。
    await next_request_minute(engine, owner)
    view = await config.patch(
        owner,
        MonitorPatch(expected_version=view.version, repeat_limit=3, interval_minutes=60),
        new_id(),
    )
    await collect(engine, owner, "9.00")
    rows = await slots(engine, owner)
    assert rows[-1]["ordinal"] == 3
    view = await config.patch(
        owner, MonitorPatch(expected_version=view.version, repeat_limit=2), new_id()
    )
    assert (await slots(engine, owner))[-1]["state"] == "cancelled"
    view = await config.patch(
        owner, MonitorPatch(expected_version=view.version, repeat_limit=3), new_id()
    )
    # 独立采集周期跨分钟；只推进合成受理时间，持久请求/每日计数保持。
    await next_request_minute(engine, owner)
    await collect(engine, owner, "8.00")
    rows = await slots(engine, owner)
    assert rows[-1]["ordinal"] == 3 and rows[-1]["id"] != rows[-2]["id"]
    await accepted(engine, rows[-1])
    await collect(engine, owner, "7.00")
    assert len(await slots(engine, owner)) == 4
    await collect(engine, owner, "21.00")
    await collect(engine, owner, "19.00")
    rows = await slots(engine, owner)
    assert rows[-1]["ordinal"] == 1 and rows[-1]["episode_id"] != rows[0]["episode_id"]
    await accepted(engine, rows[-1])
    # 跨事件冷却：模拟刚取得过许可，保存阈值不能刷出新邮件。
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE alert_slots SET authorized_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=rows[-1]["id"],
        )
    view = await config.patch(
        owner, MonitorPatch(expected_version=view.version, threshold="30.00"), new_id()
    )
    await collect(engine, owner, "5.00")
    assert len(await slots(engine, owner)) == len(rows)
    print("严格阈值/负余额、回差重武装、样本防重、未知占名额、次数迁移/降低/释放、跨事件冷却：通过")
    baseline = None
    await next_request_minute(engine, owner)
    for cycle in range(4):
        run = await accept_run(engine, owner, str(new_id()), new_id())
        execution = await claim_run(engine, UUID(bytes=run["id"]))
        await fail(engine, execution, "SCHOOL_TIMEOUT", False, new_id())
        async with engine.connect() as conn:
            monitor = await first(
                conn, "SELECT * FROM monitors WHERE owner_user_id=:id", id=owner.bytes
            )
            faults = await first(
                conn,
                "SELECT COUNT(*) AS n FROM monitor_fault_episodes WHERE monitor_id=:id",
                id=monitor["id"],
            )
        baseline = baseline or monitor["last_sample_id"]
        assert monitor["last_sample_id"] == baseline and faults["n"] == int(cycle == 3)
    await collect(engine, owner, "40.00")
    async with engine.connect() as conn:
        fault = await first(
            conn,
            "SELECT f.* FROM monitor_fault_episodes f JOIN monitors m ON m.id=f.monitor_id "
            "WHERE m.owner_user_id=:id",
            id=owner.bytes,
        )
        assert fault["closed_at"] is not None
    await config.patch(owner, MonitorPatch(expected_version=view.version, enabled=False), new_id())
    print("四个失败周期独立去重故障、失败不移动样本基线/不耗低余额额度、成功关闭故障：通过")


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用一次性验收环境")
    apps, _ = await fixture_apps()
    try:
        await verify(apps["monitoring"])
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            traceback.print_exc()
        raise SystemExit(f"T5事件验收失败（{type(error).__name__}）") from None
