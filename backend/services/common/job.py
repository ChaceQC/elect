"""已实现的 Relay/Audit 进程：故障退避、进度心跳与优雅退出。"""

import argparse
import asyncio
import signal
import sys
from types import SimpleNamespace

from sqlalchemy import text

from .background import require_standalone
from .broker import Broker, verified_event
from .database import create_database, database_ready, migration_head
from .heartbeat import Heartbeat
from .internal_dto import EventEnvelope
from .logging import configure_logging, log
from .outbox import claim_event, consume_once, finish_event
from .runtime import load_runtime, side_effect_policy
from .security import validate_keys


async def relay_tick(engine, broker):
    claim = await claim_event(engine)
    if not claim:
        return False
    try:
        event = EventEnvelope.model_validate(claim["payload"])
        await broker.publish(event)
    except Exception:
        await finish_event(engine, claim, published=False)
        raise
    await finish_event(engine, claim, published=True)
    return True


async def audit_tick(engine, runtime, queue):
    message = await queue.get(fail=False, timeout=3)
    if message is None:
        # 实际读库保证心跳反映持久化能力。
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return False
    try:
        event = verified_event(runtime, message)
        if event.type != "audit.recorded":
            raise ValueError("未登记的审计消息")
    except Exception:
        await message.reject(requeue=False)
        log("event_rejected", service="audit", error_code="INVALID_EVENT")
        return False
    from services.audit.receiver import record_audit

    try:
        changed = await consume_once(engine, "audit.recorded", event, record_audit)
    except Exception:
        await message.nack(requeue=True)
        raise
    # Inbox 与审计已提交后才 ACK；崩溃重投只命中 Inbox。
    await message.ack()
    return changed


async def run_job(service, role):
    require_standalone()
    runtime = load_runtime(service)
    validate_keys(runtime)
    side_effect_policy()
    if not runtime.db_url or not runtime.amqp_url or (role == "audit" and service != "audit"):
        raise RuntimeError("角色配置不正确")
    engine = create_database(runtime.db_url.get_secret_value())
    heartbeat, stop = Heartbeat(service, role), asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    app = SimpleNamespace(state=SimpleNamespace(
        runtime=runtime, database=engine, migration_head=migration_head(service)
    ))
    try:
        await transport_loop(app, stop, heartbeat)
    finally:
        await engine.dispose()


async def transport_loop(app, stop, heartbeat, hub=None):
    engine, runtime = app.state.database, app.state.runtime
    delay = 1
    broker = None
    try:
        while not stop.is_set():
            broker = Broker(runtime, hub=hub)
            try:
                await database_ready(engine, app.state.migration_head)
                await broker.open()
                queue = (
                    await broker.audit_queue() if heartbeat.document["role"] == "audit" else None
                )
                delay = 1
                while not stop.is_set():
                    async with asyncio.timeout(15):
                        activity = (
                            await audit_tick(engine, runtime, queue)
                            if queue
                            else await relay_tick(engine, broker)
                        )
                    connected = broker.connection.connected.is_set()
                    heartbeat.write(healthy=connected, activity=activity)
                    await pause(stop, 0.1 if activity else 1)
            except Exception:
                heartbeat.write(healthy=False)
                log("job_retry", service=runtime.service, error_code="DEPENDENCY_UNAVAILABLE")
            finally:
                await broker.close()
                broker = None
            await pause(stop, delay)
            delay = min(30, delay * 2)
    finally:
        if broker:
            await broker.close()


async def pause(stop, seconds):
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--role", choices=["relay", "audit"], required=True)
    args = parser.parse_args()
    configure_logging()
    try:
        asyncio.run(run_job(args.service, args.role))
    except Exception:
        log("job_start_failed", service=args.service, error_code="INVALID_RUNTIME")
        sys.exit(1)


if __name__ == "__main__":
    main()
