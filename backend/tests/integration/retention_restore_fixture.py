"""仅供独立R4恢复脚本；固定内部主机、合成七库、无业务Secret。"""

import asyncio
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

from query_resource_support import migrate, seed_binding
from sqlalchemy.ext.asyncio import create_async_engine

from services.common.archive_verify import verify_archives, verify_cold_links
from services.common.domains import DATABASES
from services.common.outbox import consume_once
from services.common.sql import execute, first
from services.deployment.recovery_rules import OUTBOX_HOLD, RULES
from services.deployment.retention import batch
from services.room.balance import accept_refresh
from services.room.repository import RoomRepository

ID = UUID("0199a10c-0000-7000-8000-000000000001")
BINDING = UUID("0199a10c-0000-7000-8000-000000000002")
KEY = "r4-synthetic-original-request"


async def effect(conn, _):
    await execute(conn, "UPDATE synthetic_effects SET n=n+1")


async def seed(engine, domain):
    async with engine.begin() as conn:
        await conn.run_sync(migrate, domain)
        await conn.run_sync(migrate, domain)
        await execute(conn, "CREATE TABLE synthetic_effects (n INT NOT NULL)")
        await execute(conn, "INSERT INTO synthetic_effects VALUES (0)")
    await consume_once(engine, "r4.restore", SimpleNamespace(event_id=ID), effect)
    async with engine.begin() as conn:
        await execute(conn, "UPDATE inbox_events SET created_at='2000-01-01',"
                      "updated_at='2000-01-01',processed_at='2000-01-01'")
        await execute(conn, "INSERT INTO outbox_events (event_id,type,schema_version,aggregate_id,"
            "aggregate_version,payload,available_at,publish_attempts) VALUES "
            "(:id,'synthetic',1,:id,1,'{}',UTC_TIMESTAMP(6),0)", id=ID.bytes)
    await batch(engine, domain, "inbox_events", datetime(2026, 1, 1), apply=True)
    if domain == "room":
        await seed_binding(engine, ID, BINDING)
        await accept_refresh(engine, ID, BINDING, KEY)
        async with engine.begin() as conn:
            await execute(conn, "UPDATE room_operations SET state='succeeded',saga_step='complete',"
                "next_reconcile_at=NULL,created_at='2000-01-01',updated_at='2000-01-01'")
        await batch(engine, domain, "room_operations", datetime(2026, 1, 1), apply=True)
    if domain == "notification":
        async with engine.begin() as conn:
            await execute(conn, "INSERT INTO notification_jobs (id,alert_slot_id,owner_user_id,"
                "email_ciphertext,generation,email_version,template_version,message_id,state,"
                "version,attempt_count,execution_epoch,body_started_at) VALUES "
                "(:id,:id,:id,:encrypted,1,1,'synthetic','synthetic','delivery_unknown',1,1,1,"
                "UTC_TIMESTAMP(6))", id=ID.bytes, encrypted=b"synthetic-encrypted")
    if domain == "school_adapter":
        async with engine.begin() as conn:
            for index, kind in enumerate(("create_order", "E02", "E03")):
                await execute(conn, "INSERT INTO upstream_operations "
                    "(id,owner_user_id,operation_type,"
                    "target_ref,request_digest,credential_version,state,dispatched_at) "
                    "VALUES (:id,:owner,:kind,'synthetic',:digest,1,'unknown',UTC_TIMESTAMP(6))",
                    id=UUID(int=ID.int+index).bytes, owner=ID.bytes, kind=kind, digest=b"0"*32)


async def verify(engine, domain):
    async with engine.begin() as conn:
        assert await verify_archives(conn) >= 1
        await verify_cold_links(conn)
        for statement in RULES.get(domain, []):
            await execute(conn, statement)
        await execute(conn, OUTBOX_HOLD)
    assert not await consume_once(engine, "r4.restore", SimpleNamespace(event_id=ID), effect)
    async with engine.connect() as conn:
        assert (await first(conn, "SELECT n FROM synthetic_effects"))["n"] == 1
        assert (await first(conn, "SELECT YEAR(available_at) AS y FROM outbox_events"))["y"] == 9999
        if domain == "notification":
            row = await first(conn, "SELECT * FROM notification_jobs")
            assert row["state"] == "delivery_unknown" and row["body_started_at"] is not None
        if domain == "school_adapter":
            assert (await first(conn, "SELECT COUNT(*) AS n FROM upstream_operations "
                "WHERE state='unknown' AND dispatched_at IS NOT NULL"))["n"] == 3
    if domain == "room":
        op = await accept_refresh(engine, ID, BINDING, KEY)
        assert (await RoomRepository(engine).operation(ID, op))["state"] == "succeeded"


async def main(mode):
    host = os.environ["ELECT_R4_RESTORE_HOST"]
    if host not in {"r4-source", "r4-target"}:
        raise ValueError("仅允许隔离R4主机")
    for domain, name in DATABASES.items():
        root = create_async_engine(f"mysql+asyncmy://root@{host}/mysql", hide_parameters=True)
        if mode == "seed":
            async with root.begin() as conn:
                await execute(conn, f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
        await root.dispose()
        engine = create_async_engine(f"mysql+asyncmy://root@{host}/{name}",
                                     pool_size=2, max_overflow=1, hide_parameters=True,
                                     isolation_level="READ COMMITTED")
        try:
            await (seed if mode == "seed" else verify)(engine, domain)
        finally:
            await engine.dispose()
    print("R4 seven-domain " + mode + " passed")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
