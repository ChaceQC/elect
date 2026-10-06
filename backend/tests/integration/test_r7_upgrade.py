"""从审计0.19.2的七域旧头升级；保留旧记录，重复运行正式迁移入口。"""

import asyncio

import pytest
from query_resource_support import database, requires_mysql, seed_binding

from services.common.database import migration_head
from services.common.ids import new_id
from services.common.sql import execute, first
from services.migrate_all_mysql import migrate_domain

pytestmark = requires_mysql
BASELINES = {"identity": "identity_0003", "school_adapter": "school_0006",
             "room": "room_0005", "monitoring": "monitoring_0006",
             "notification": "notification_0002", "payment": "payment_0004",
             "audit": "audit_0001"}


@pytest.mark.parametrize("domain", BASELINES)
def test_old_domain_records_survive_repeated_upgrade(domain):
    async def case():
        async with database(domain, revision=BASELINES[domain]) as engine:
            event, owner, binding = new_id(), new_id(), new_id()
            async with engine.begin() as conn:
                await execute(conn, "INSERT INTO inbox_events "
                    "(consumer_name,event_id,processed_at) VALUES ('r7.old',:id,UTC_TIMESTAMP(6))",
                    id=event.bytes)
            if domain == "room":
                await seed_binding(engine, owner, binding)
                async with engine.begin() as conn:
                    await execute(conn, "INSERT INTO room_balance_cache "
                        "(binding_id,balance,source,quality) VALUES (:id,25.50,'B02','stale')",
                        id=binding.bytes)
            for _ in range(2):
                await migrate_domain(domain, engine.url)
            async with engine.connect() as conn:
                assert (await first(conn, "SELECT version_num FROM alembic_version"))[
                    "version_num"] == migration_head(domain)
                inbox = await first(conn, "SELECT processed_at FROM inbox_events "
                                    "WHERE event_id=:id", id=event.bytes)
                assert inbox["processed_at"]
                assert (await first(conn, "SELECT COUNT(*) AS n FROM cold_inbox_events"))["n"] == 0
                assert (await first(conn, "SELECT COUNT(*) AS n FROM archive_records"))["n"] == 0
                if domain == "room":
                    row = await first(conn, "SELECT balance,observation_sequence "
                                      "FROM room_balance_cache WHERE binding_id=:id",
                                      id=binding.bytes)
                    assert row["balance"] == 25.50 and row["observation_sequence"] is None
                if domain == "school_adapter":
                    assert (await first(conn,
                        "SELECT COUNT(*) AS n FROM balance_observation_counters"))["n"] == 0
    asyncio.run(case())
