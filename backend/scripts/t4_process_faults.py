"""真实SIGKILL、持久租约恢复与RabbitMQ重复/丢失提示检查。"""

import asyncio
import sys

from services.common.broker import Broker
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.sql import execute, first
from services.monitoring.job import message_tick
from services.monitoring.recovery import recovery_tick
from services.monitoring.scheduler import wake


async def kill_claim(engine, run_id):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.t4_claim_process",
        "--run-id",
        str(run_id),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 15) == b"claimed\n"
        process.kill()
        assert await process.wait() == -9
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    async with engine.begin() as conn:
        row = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=run_id.bytes)
        assert row["state"] == "running" and row["lease_owner"]
        await execute(
            conn,
            "UPDATE monitor_runs SET lease_until=UTC_TIMESTAMP(6) WHERE id=:id",
            id=run_id.bytes,
        )
    assert await recovery_tick(engine)
    async with engine.begin() as conn:
        restored = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=run_id.bytes)
        assert (
            restored["state"] == "retry_wait"
            and restored["execution_epoch"] > row["execution_epoch"]
        )
        await execute(
            conn,
            "UPDATE monitor_runs SET next_attempt_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=run_id.bytes,
        )


async def duplicate_message(app, run_id):
    broker = Broker(app.state.runtime)
    await broker.open()
    try:
        queue = await broker.channel.declare_queue("elect.monitoring.runs", durable=True)
        await queue.purge()
        async with app.state.database.begin() as conn:
            run = await first(conn, "SELECT * FROM monitor_runs WHERE id=:id", id=run_id.bytes)
            await wake(conn, run, new_id())
            raw = await first(
                conn,
                "SELECT payload FROM outbox_events WHERE aggregate_id=:id "
                "AND type='monitor.run_ready' ORDER BY created_at DESC,event_id DESC LIMIT 1",
                id=run["monitor_id"],
            )
        event = EventEnvelope.model_validate_json(raw["payload"])
        await broker.publish(event)
        await broker.publish(event)
        assert await message_tick(app, queue, None)
        assert await message_tick(app, queue, None)
        async with app.state.database.connect() as conn:
            count = await first(
                conn, "SELECT COUNT(*) AS n FROM monitor_samples WHERE run_id=:id", id=run_id.bytes
            )
            inbox = await first(
                conn,
                "SELECT COUNT(*) AS n FROM inbox_events WHERE consumer_name='monitor.run_ready' "
                "AND event_id=:id",
                id=event.event_id.bytes,
            )
            assert count["n"] == 1 and inbox["n"] == 1
    finally:
        await broker.close()
    print("SIGKILL领取进程/租约恢复、真实RabbitMQ重复提示只一个样本/Inbox：通过")
