"""显式一次性容器验收，仅读写合成基础设施事件，无学校/邮件副作用。"""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from services.audit.receiver import record_audit
from services.common.broker import Broker
from services.common.database import create_database, migration_head
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.logging import configure_logging
from services.common.migration_runtime import DATABASES
from services.common.outbox import append_event, claim_event, consume_once, finish_event
from services.common.runtime import Runtime, read_secret
from services.common.security import issue_token
from services.migrate_all_mysql import migrate_domain, migration_urls


def fixture_event():
    identifier = new_id()
    return EventEnvelope(
        event_id=identifier,
        type="audit.recorded",
        schema_version=1,
        producer="identity",
        aggregate_id=new_id(),
        aggregate_version=1,
        occurred_at=datetime.now(UTC),
        request_id=new_id(),
        payload={
            "action": "foundation.smoke",
            "object_type": "fixture",
            "object_id": new_id(),
            "result": "succeeded",
            "actor_user_id": new_id(),
        },
        dedupe_key=str(identifier),
    )


async def isolated_empty_databases(engines):
    for domain, engine in engines.items():
        async with engine.connect() as connection:
            assert (
                await connection.execute(text("SELECT @@session.time_zone"))
            ).scalar() == "+00:00"
            assert (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar() == migration_head(domain)
            for row in await connection.execute(text("SHOW TABLES")):
                if row[0] != "alembic_version":
                    assert (
                        await connection.execute(text(f"SELECT COUNT(*) FROM `{row[0]}`"))
                    ).scalar() == 0
            for statement in (
                "CREATE TABLE forbidden_ddl (id INT)",
                "SELECT * FROM elect_room.alembic_version"
                if domain != "room"
                else "SELECT * FROM elect_identity.alembic_version",
            ):
                try:
                    await connection.execute(text(statement))
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("领域权限隔离失败")


async def verify_leases_and_transactions(engine):
    event = fixture_event()
    async with engine.begin() as connection:
        await append_event(connection, event)
    claims = await asyncio.gather(claim_event(engine, 1), claim_event(engine, 1))
    assert sum(claim is not None for claim in claims) == 1
    first = next(claim for claim in claims if claim)
    await asyncio.sleep(1.2)
    second = await claim_event(engine)
    assert second and second["owner"] != first["owner"]
    assert not await finish_event(engine, first, published=True)
    assert await finish_event(engine, second, published=False)
    assert await claim_event(engine) is None  # 按退避时间再领取。

    async def failed_handler(connection, envelope):
        await record_audit(connection, envelope)
        raise RuntimeError("synthetic crash before commit")

    try:
        await consume_once(engine, "smoke.transaction", event, failed_handler)
    except RuntimeError:
        pass
    else:
        raise AssertionError("预期的事务失败未发生")
    async with engine.connect() as connection:
        assert (await connection.execute(text("SELECT COUNT(*) FROM audit_events"))).scalar() == 0
        assert (await connection.execute(text("SELECT COUNT(*) FROM inbox_events"))).scalar() == 0
    results = await asyncio.gather(
        *(consume_once(engine, "smoke.transaction", event, record_audit) for _ in range(2))
    )
    assert sorted(results) == [False, True]
    async with engine.begin() as connection:
        for table in ("outbox_events", "inbox_events", "audit_events"):
            await connection.execute(
                text(f"DELETE FROM {table} WHERE event_id=:id"), {"id": event.event_id.bytes}
            )


async def verify_context_and_redis(runtimes):
    async with httpx.AsyncClient(timeout=5) as client:
        sender = runtimes["identity"]
        for receiver in DATABASES:
            host = "school-adapter" if receiver == "school_adapter" else receiver
            assert (await client.get(f"http://{host}:8000/health/ready")).status_code == 200
            user = new_id()
            token = issue_token(
                sender, receiver, "foundation:read", new_id(), user_id=user, session_version=1
            )
            response = await client.get(
                f"http://{host}:8000/internal/v1/context",
                headers={"Authorization": f"Bearer {token}", "X-User-Id": str(new_id())},
            )
            assert response.status_code == 200 and response.json()["user_id"] == str(user)
        forged = await client.get(
            "http://room:8000/internal/v1/context", headers={"X-User-Id": str(new_id())}
        )
        assert forged.status_code == 401
    cache = Redis.from_url(runtimes["identity"].redis_url.get_secret_value())
    try:
        assert await cache.ping()
        await cache.set("identity:smoke", "synthetic")
        assert await cache.get("identity:smoke") == b"synthetic"
        try:
            await cache.get("room:forbidden")
        except Exception:
            pass
        else:
            raise AssertionError("Redis 前缀隔离失败")
        await cache.delete("identity:smoke")
    finally:
        await cache.aclose()


async def verify_live_duplicate_event(runtimes, engines):
    event = fixture_event()
    broker = Broker(runtimes["identity"])
    try:
        await broker.open()
        async with engines["identity"].begin() as connection:
            await append_event(connection, event)
        # 同一消息重复发布，并由实际 Relay 再发布一次。
        await broker.publish(event)
        await broker.publish(event)
        for _ in range(30):
            async with engines["audit"].connect() as connection:
                count = (
                    await connection.execute(
                        text("SELECT COUNT(*) FROM audit_events WHERE event_id=:id"),
                        {"id": event.event_id.bytes},
                    )
                ).scalar()
            async with engines["identity"].connect() as connection:
                published = (
                    await connection.execute(
                        text("SELECT published_at FROM outbox_events WHERE event_id=:id"),
                        {"id": event.event_id.bytes},
                    )
                ).scalar()
            if count == 1 and published:
                break
            await asyncio.sleep(1)
        else:
            raise AssertionError("Relay/Audit 持久投递未完成")
        await asyncio.sleep(1)
        async with engines["audit"].connect() as connection:
            assert (
                await connection.execute(
                    text("SELECT COUNT(*) FROM inbox_events WHERE event_id=:id"),
                    {"id": event.event_id.bytes},
                )
            ).scalar() == 1
        # 保留一条合成事件，供重建容器后的持久卷检查；业务表仍为空。
        print("实际 Relay + 重复消息 + Audit/Inbox：通过")
    finally:
        await broker.close()


async def main():
    configure_logging()
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("只能在显式一次性验收环境执行")
    runtimes = {
        domain: Runtime.model_validate_json(
            read_secret(Path("/run/secrets") / f"{domain}_runtime.json")
        )
        for domain in DATABASES
    }
    engines = {
        domain: create_database(runtime.db_url.get_secret_value())
        for domain, runtime in runtimes.items()
    }
    try:
        await isolated_empty_databases(engines)
        print("七域空库、UTC、运行账号无跨库/DDL：通过")
        for domain, url in migration_urls().items():
            await asyncio.gather(migrate_domain(domain, url), migrate_domain(domain, url))
        print("七域重复/并发持锁迁移：通过")
        await verify_leases_and_transactions(engines["audit"])
        print("并发领取、租约接管、旧领取者栅栏、退避、Inbox 事务：通过")
        await verify_context_and_redis(runtimes)
        print("实际服务 JWT/用户上下文、Redis ACL：通过")
        await verify_live_duplicate_event(runtimes, engines)
    finally:
        for engine in engines.values():
            await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        raise SystemExit("容器验收失败；检查最后一个通过的步骤和脱敏服务日志") from None
