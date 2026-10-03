"""实际MySQL/MQ的提交提示、扫描退避和推送回归；只使用合成审计。"""

import argparse
import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import event as sql_event

from scripts.deployment_smoke import fixture_event
from scripts.monitoring_combined_smoke import until
from services.audit.receiver import record_audit
from services.common.broker import Broker, verified_event
from services.common.database import create_database, migration_head
from services.common.heartbeat import Heartbeat
from services.common.job import transport_loop
from services.common.logging import configure_logging
from services.common.outbox import append_event, consume_once
from services.common.runtime import Runtime, read_secret
from services.common.sql import first


async def published(engine, identifier):
    async with engine.connect() as conn:
        row = await first(conn, "SELECT published_at FROM outbox_events WHERE event_id=:id",
                          id=identifier.bytes)
    return bool(row and row["published_at"])


async def empty(engine):
    async with engine.connect() as conn:
        row = await first(conn, "SELECT COUNT(*) AS n FROM outbox_events "
                          "WHERE published_at IS NULL")
    return row["n"] == 0


async def verify_relay(runtimes, engines):
    engine, stop, scans = engines["identity"], asyncio.Event(), []

    def counted(conn, cursor, statement, *args):
        if statement.startswith("SELECT event_id,payload,publish_attempts FROM outbox_events"):
            scans.append(time.monotonic())

    sql_event.listen(engine.sync_engine, "after_cursor_execute", counted)
    tasks = []
    for name, role in [("identity", "relay"), ("audit", "audit")]:
        app = SimpleNamespace(state=SimpleNamespace(
            runtime=runtimes[name], database=engines[name], migration_head=migration_head(name),
        ))
        tasks.append(asyncio.create_task(
            transport_loop(app, stop, Heartbeat(name, role, max_age=45)),
        ))
    try:
        await until(lambda: empty(engine), seconds=60)
        baseline = len(scans)
        await asyncio.sleep(11)
        idle_scans = len(scans) - baseline
        assert 1 <= idle_scans <= 6, idle_scans
        rollback = fixture_event()
        engine.outbox_wakeup.event.clear()
        try:
            async with engine.begin() as conn:
                await append_event(conn, rollback)
                assert not engine.outbox_wakeup.event.is_set()
                raise ValueError("synthetic rollback")
        except ValueError:
            pass
        assert not engine.outbox_wakeup.event.is_set()
        async with engine.connect() as conn:
            assert not await first(conn, "SELECT event_id FROM outbox_events WHERE event_id=:id",
                                   id=rollback.event_id.bytes)
        committed = fixture_event()
        started = time.monotonic()
        async with engine.begin() as conn:
            await append_event(conn, committed)
            assert not engine.outbox_wakeup.event.is_set()
            async with engine.connect() as reader:
                assert not await first(reader, "SELECT event_id FROM outbox_events "
                                       "WHERE event_id=:id", id=committed.event_id.bytes)
        await until(lambda: published(engine, committed.event_id), seconds=2)
        latency = time.monotonic() - started
        # 独立engine提示不会跨进程/池传播，Relay仍须由最多10秒扫描发现。
        other = create_database(runtimes["identity"].db_url.get_secret_value())
        try:
            unhinted = fixture_event()
            async with other.begin() as conn:
                await append_event(conn, unhinted)
            await until(lambda: published(engine, unhinted.event_id), seconds=12)
        finally:
            await other.dispose()
        print({"idle_window_seconds": 11, "relay_sql_scans": idle_scans,
               "commit_to_confirm_seconds": round(latency, 4), "rollback_no_hint": True,
               "unhinted_persistent_scan": True})
    finally:
        stop.set()
        await asyncio.gather(*tasks)
        sql_event.remove(engine.sync_engine, "after_cursor_execute", counted)


async def receive(consumer):
    async with asyncio.timeout(20):
        while True:
            message = await consumer.get()
            if message:
                return message
            await consumer.wait(asyncio.Event(), 1)


async def verify_push(runtimes, engines, directory):
    producer, consumer_broker = Broker(runtimes["identity"]), Broker(runtimes["audit"])
    try:
        await producer.open()
        await consumer_broker.open()
        consumer = await consumer_broker.consume(await consumer_broker.audit_queue())
        # 先按真实处理边界排空本隔离项目的既有合成消息。
        while True:
            await consumer.wait(asyncio.Event(), 0.5)
            message = await consumer.get()
            if message is None:
                break
            event = verified_event(runtimes["audit"], message)
            await consume_once(engines["audit"], "audit.recorded", event, record_audit)
            await message.ack()
        event = fixture_event()
        await producer.publish(event)
        held = await receive(consumer)
        assert held.message_id == str(event.event_id) and not held.processed
        directory.joinpath("ready").touch()
        async with asyncio.timeout(90):
            while not directory.joinpath("reconnected").exists():
                await asyncio.sleep(0.2)
        await until(lambda: invalidated(consumer), seconds=20)
        assert not held.processed
        await consumer_broker.close()
        # 丢线前未ACK的消息由RabbitMQ重投，显式新consumer不继承旧缓冲。
        consumer_broker = Broker(runtimes["audit"])
        await consumer_broker.open()
        consumer = await consumer_broker.consume(await consumer_broker.audit_queue())
        redelivered = await receive(consumer)
        assert redelivered.message_id == str(event.event_id) and redelivered.redelivered

        async def failed(conn, envelope):
            await record_audit(conn, envelope)
            raise ValueError("synthetic rollback before ACK")

        try:
            await consume_once(engines["audit"], "audit.recorded", event, failed)
        except ValueError:
            await redelivered.nack(requeue=True)
        else:
            raise AssertionError("Inbox事务未回滚")
        async with engines["audit"].connect() as conn:
            assert not await first(conn, "SELECT event_id FROM inbox_events WHERE event_id=:id",
                                   id=event.event_id.bytes)
        message = await receive(consumer)
        verified = verified_event(runtimes["audit"], message)
        assert await consume_once(engines["audit"], "audit.recorded", verified, record_audit)
        assert not message.processed
        await message.ack()
        await producer.close()
        producer = Broker(runtimes["identity"])
        await producer.open()
        for _ in range(2):
            await producer.publish(event)
            duplicate = await receive(consumer)
            assert not await consume_once(
                engines["audit"], "audit.recorded", verified_event(runtimes["audit"], duplicate),
                record_audit,
            )
            await duplicate.ack()
        async with engines["audit"].connect() as conn:
            for table in ("audit_events", "inbox_events"):
                row = await first(conn, f"SELECT COUNT(*) AS n FROM {table} WHERE event_id=:id",
                                  id=event.event_id.bytes)
                assert row["n"] == 1
        print("实际推送/prefetch=1、断线未ACK重投、事务回滚后重投、提交后ACK/重复唯一：通过")
    finally:
        await producer.close()
        await consumer_broker.close()


async def invalidated(consumer):
    return consumer.invalid


async def main(mode):
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅允许一次性环境")
    configure_logging()
    runtimes = {name: Runtime.model_validate_json(read_secret(f"/run/secrets/{name}_runtime.json"))
                for name in ("identity", "audit")}
    engines = {name: create_database(runtime.db_url.get_secret_value())
               for name, runtime in runtimes.items()}
    try:
        if mode == "relay":
            await verify_relay(runtimes, engines)
        else:
            await verify_push(runtimes, engines, Path("/run/efficiency"))
    finally:
        for engine in engines.values():
            await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["relay", "push"])
    try:
        asyncio.run(main(parser.parse_args().mode))
    except Exception:
        raise SystemExit("Outbox/推送隔离验收失败；未输出凭据或消息载荷") from None
