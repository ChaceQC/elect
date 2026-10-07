"""完整恢复apply接线：新观测/修复别名/七域冷热标识及低水位失败后仍隔离。"""

import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace

import pytest
from query_resource_support import database, requires_mysql, seed_binding

from scripts.r7_recovery_data import seed, verify
from services.common.domains import DATABASES
from services.common.ids import new_id
from services.common.sql import execute, first
from services.deployment import recovery_guard
from services.deployment.recovery_observations import ObservationWatermarkError

pytestmark = requires_mysql


def test_full_guard_keeps_isolation_on_watermark_failure(monkeypatch):
    monkeypatch.setenv("ELECT_RECOVERY_ISOLATED", "1")

    async def case():
        async with AsyncExitStack() as stack:
            engines = {name: await stack.enter_async_context(database(name)) for name in DATABASES}
            apps = {name: SimpleNamespace(state=SimpleNamespace(database=engine))
                    for name, engine in engines.items()}
            monkeypatch.setattr(recovery_guard, "migration_urls",
                                lambda: {name: engine.url for name, engine in engines.items()})
            owner, binding = new_id(), new_id()
            await seed_binding(engines["room"], owner, binding)
            async with engines["room"].begin() as conn:
                await execute(conn, "INSERT INTO room_preferences "
                    "(owner_user_id,default_binding_id,version,state) VALUES (:o,:b,1,'ready')",
                    o=owner.bytes, b=binding.bytes)
            state = {"owner": str(owner)}
            state["r7"] = await seed(apps, state)
            for engine in engines.values():
                async with engine.begin() as conn:
                    await execute(conn, "INSERT INTO outbox_events "
                        "(event_id,type,schema_version,aggregate_id,aggregate_version,payload,"
                        "available_at,publish_attempts) VALUES "
                        "(:id,'synthetic',1,:id,1,'{}',UTC_TIMESTAMP(6),0)", id=new_id().bytes)
            await recovery_guard.run("apply")
            await recovery_guard.run("apply")
            await verify(apps, state)
            async with engines["school_adapter"].begin() as conn:
                await execute(conn, "DELETE FROM balance_observation_counters")
            with pytest.raises(ObservationWatermarkError):
                await recovery_guard.run("apply")
            for engine in engines.values():
                async with engine.connect() as conn:
                    assert not (await first(conn, "SELECT COUNT(*) AS n FROM outbox_events "
                        "WHERE published_at IS NULL AND YEAR(available_at)<>9999"))["n"]
    asyncio.run(case())
