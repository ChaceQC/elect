"""配置触发采集与手动采集共享真实MySQL预算；只使用合成用户。"""

import asyncio
import os
from datetime import timedelta

import pytest
from query_resource_support import counts, database, requires_mysql

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import execute, first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.email_crypto import EmailCrypto
from services.monitoring.repository import lock_monitor
from services.monitoring.scheduler import accept_run, scheduler_tick

pytestmark = requires_mysql
TABLES = ["monitor_run_requests", "monitor_runs", "outbox_events"]


async def setup(engine):
    owner, binding = new_id(), new_id()
    crypto = EmailCrypto("test", {"test": os.urandom(32)})
    async with engine.begin() as conn:
        await lock_monitor(conn, owner)
        await execute(
            conn, "UPDATE monitors SET state='active',desired_enabled=1,"
            "credential_allowed=1,credential_version=1,credential_ref=:binding,"
            "binding_id=:binding,email_ciphertext=:email,"
            "schedule_anchor_at=UTC_TIMESTAMP(6),"
            "next_run_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 60 MINUTE) "
            "WHERE owner_user_id=:owner", owner=owner.bytes, binding=binding.bytes,
            email=crypto.seal("student@example.invalid", owner, 1),
        )
    return owner, MonitorConfiguration(engine, crypto)


async def patch(config, owner, **changes):
    current = await config.get(owner)
    return await config.patch(
        owner, MonitorPatch(expected_version=current.version, **changes), new_id(),
    )


async def finish(engine, owner):
    async with engine.begin() as conn:
        await execute(conn, "UPDATE monitor_runs r JOIN monitors m ON m.id=r.monitor_id "
                      "SET r.state='succeeded',r.finished_at=UTC_TIMESTAMP(6) "
                      "WHERE m.owner_user_id=:owner", owner=owner.bytes)
        await execute(conn, "UPDATE monitors SET active_run_id=NULL WHERE owner_user_id=:owner",
                      owner=owner.bytes)


async def snapshot(engine, owner):
    async with engine.connect() as conn:
        monitor = await first(conn, "SELECT * FROM monitors WHERE owner_user_id=:owner",
                              owner=owner.bytes)
        runs = (await execute(conn, "SELECT * FROM monitor_runs WHERE monitor_id=:id ORDER BY id",
                              id=monitor["id"])).mappings().all()
    return monitor, await counts(engine, TABLES), runs


def test_interval_switches_are_charged_and_rejection_leaves_schedule_unchanged():
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owner, config = await setup(engine)
            for interval in [61, 60] * 3:
                saved = await patch(config, owner, interval_minutes=interval)
                assert saved.current_run is not None
                assert saved.next_run_at - saved.current_run.scheduled_for == timedelta(
                    minutes=interval,
                )
                await finish(engine, owner)
            before = await snapshot(engine, owner)
            assert before[1][0] == 6
            for _ in range(2):
                with pytest.raises(ApiError) as error:
                    await patch(config, owner, interval_minutes=61)
                assert error.value.status == 429 and error.value.retry_after_seconds > 0
                assert await snapshot(engine, owner) == before
    asyncio.run(case())


def test_manual_and_config_requests_share_budget_replay_and_close_still_work():
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owner, config = await setup(engine)
            key = str(new_id())
            original = await accept_run(engine, owner, key, new_id())
            for _ in range(4):
                await accept_run(engine, owner, str(new_id()), new_id())
            saved = await patch(config, owner, interval_minutes=61)
            before = await snapshot(engine, owner)
            assert before[1][0] == 6
            with pytest.raises(ApiError) as error:
                await accept_run(engine, owner, str(new_id()), new_id())
            assert error.value.status == 429
            replay = await accept_run(engine, owner, key, new_id())
            assert replay["id"] == original["id"] and replay["state"] == "cancelled"
            assert (await patch(config, owner, interval_minutes=61)).version == saved.version
            assert await snapshot(engine, owner) == before
            changed = await patch(config, owner, threshold="21.00")
            assert changed.next_run_at == saved.next_run_at
            assert not await scheduler_tick(engine)
            assert (await counts(engine, TABLES))[0] == 6
            assert (await patch(config, owner, enabled=False)).state == "disabled"
            before = await snapshot(engine, owner)
            with pytest.raises(ApiError) as error:
                await patch(config, owner, enabled=True)
            assert error.value.status == 429
            assert await snapshot(engine, owner) == before
    asyncio.run(case())


def test_manual_quota_exhaustion_rejects_config_before_invalidating_active_run():
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owner, config = await setup(engine)
            for _ in range(6):
                await accept_run(engine, owner, str(new_id()), new_id())
            before = await snapshot(engine, owner)
            with pytest.raises(ApiError) as error:
                await patch(config, owner, interval_minutes=61)
            assert error.value.status == 429
            assert await snapshot(engine, owner) == before
            current = await config.get(owner)
            assert current.current_run.state == "pending" and not current.cancel_pending
    asyncio.run(case())


def test_scheduler_does_not_double_collect_or_consume_manual_budget():
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owner, config = await setup(engine)
            await patch(config, owner, enabled=False)
            await patch(config, owner, enabled=True, interval_minutes=61)
            await finish(engine, owner)
            assert not await scheduler_tick(engine)
            async with engine.begin() as conn:
                await execute(conn, "UPDATE monitor_runs SET scheduled_for="
                              "DATE_SUB(scheduled_for,INTERVAL 61 MINUTE)")
                await execute(conn, "UPDATE monitors SET schedule_anchor_at="
                              "DATE_SUB(schedule_anchor_at,INTERVAL 61 MINUTE),"
                              "next_run_at=DATE_SUB(next_run_at,INTERVAL 61 MINUTE) "
                              "WHERE owner_user_id=:owner", owner=owner.bytes)
            assert await scheduler_tick(engine)
            totals = await counts(engine, TABLES)
            assert totals[0] == 1 and totals[1] == 2
    asyncio.run(case())


def test_inactive_config_drafts_do_not_consume_collection_budget():
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            for state in ["disabled", "requires_reauth", "blocked_room"]:
                owner, config = await setup(engine)
                async with engine.begin() as conn:
                    await execute(conn, "UPDATE monitors SET state=:state,desired_enabled=:enabled,"
                                  "credential_allowed=:allowed,next_run_at=NULL "
                                  "WHERE owner_user_id=:owner", state=state,
                                  enabled=state != "disabled", allowed=state != "requires_reauth",
                                  owner=owner.bytes)
                saved = await patch(config, owner, interval_minutes=61)
                assert saved.state == state and saved.next_run_at is None
            assert await counts(engine, TABLES[:2]) == [0, 0]
    asyncio.run(case())


def test_existing_alert_cycles_keep_their_limits_with_config_admission(monkeypatch):
    from types import SimpleNamespace

    from scripts.t5_alert_smoke import verify

    monkeypatch.setenv("ELECT_TEST_DISPOSABLE", "1")

    async def case():
        async with database("monitoring", production_pool=True) as engine:
            app = SimpleNamespace(state=SimpleNamespace(
                database=engine, email_crypto=EmailCrypto("test", {"test": os.urandom(32)}),
            ))
            await verify(app)
    asyncio.run(case())


@pytest.mark.parametrize("boundary", ["daily", "pending"])
def test_config_respects_daily_and_pending_limits(boundary):
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owner, config = await setup(engine)
            limit = 48 if boundary == "daily" else 8
            for index in range(limit):
                await accept_run(engine, owner, str(new_id()), new_id())
                if boundary == "daily":
                    await finish(engine, owner)
                if (index + 1) % 6 == 0 or index + 1 == limit:
                    async with engine.begin() as conn:
                        await execute(conn, "UPDATE monitor_run_requests SET created_at="
                                      "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 2 MINUTE)")
            before = await snapshot(engine, owner)
            with pytest.raises(ApiError) as error:
                await patch(config, owner, interval_minutes=61)
            assert error.value.status == 429 and error.value.retry_after_seconds > 0
            assert await snapshot(engine, owner) == before
    asyncio.run(case())


def test_config_and_manual_race_for_last_quota_slot():
    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owner, config = await setup(engine)
            for _ in range(5):
                await accept_run(engine, owner, str(new_id()), new_id())
            results = await asyncio.gather(
                patch(config, owner, interval_minutes=61),
                accept_run(engine, owner, str(new_id()), new_id()),
                return_exceptions=True,
            )
            assert sum(not isinstance(value, Exception) for value in results) == 1
            assert all(isinstance(value, ApiError) and value.status == 429 for value in results
                       if isinstance(value, Exception))
            assert (await counts(engine, TABLES))[0] == 6
    asyncio.run(case())


def test_config_run_and_schedule_roll_back_when_recording_fails(monkeypatch):
    from services.monitoring import configuration

    async def reject_record(*args):
        raise RuntimeError("synthetic admission failure")

    async def case():
        async with database("monitoring", production_pool=True) as engine:
            owner, config = await setup(engine)
            await accept_run(engine, owner, str(new_id()), new_id())
            before = await snapshot(engine, owner)
            monkeypatch.setattr(configuration, "record_request", reject_record)
            with pytest.raises(RuntimeError, match="synthetic admission failure"):
                await patch(config, owner, interval_minutes=61)
            assert await snapshot(engine, owner) == before
    asyncio.run(case())
