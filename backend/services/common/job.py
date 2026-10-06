"""已实现的 Relay/Audit 进程：故障退避、进度心跳与优雅退出。"""

import argparse
import asyncio
import sys
from types import SimpleNamespace

from .background import Role, require_standalone, run_standalone
from .broker import Broker, verified_event
from .database import create_database, database_ready, migration_head
from .internal_dto import EventEnvelope
from .logging import configure_logging, log
from .outbox import claim_event, consume_once, finish_event
from .process_control import run_managed
from .runtime import load_runtime, side_effect_policy
from .scheduling import IdleBackoff, retry_delay
from .security import validate_keys
from .transport_health import QueueUnavailable, receive, transport_scan


async def relay_tick(engine, broker):
    claim = await claim_event(engine)
    if not claim:
        return False
    try:
        event = EventEnvelope.model_validate(claim["payload"])
    except Exception:
        await finish_event(engine, claim, published=False)
        raise
    try:
        await broker.publish(event)
    except Exception:
        await finish_event(engine, claim, published=False)
        raise QueueUnavailable() from None
    await finish_event(engine, claim, published=True)
    return True


async def audit_tick(engine, runtime, queue):
    message = await receive(queue)
    if message is None:
        await transport_scan(engine, "audit")
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


async def run_job(service, role, *, control=None):
    require_standalone()
    runtime = load_runtime(service)
    validate_keys(runtime)
    side_effect_policy()
    if not runtime.db_url or not runtime.amqp_url or (role == "audit" and service != "audit"):
        raise RuntimeError("角色配置不正确")
    engine = create_database(runtime.db_url.get_secret_value())
    app = SimpleNamespace(state=SimpleNamespace(
        runtime=runtime, database=engine, migration_head=migration_head(service),
        process_control=control,
    ))
    try:
        await run_standalone(app, [Role(role, transport_loop, max_age=45)], control)
    finally:
        await engine.dispose()


async def transport_loop(app, stop, heartbeat, hub=None):
    engine, runtime = app.state.database, app.state.runtime
    failures = 0
    broker = None
    try:
        while not stop.is_set():
            broker = Broker(runtime, hub=hub)
            try:
                await database_ready(engine, app.state.migration_head)
                try:
                    async with asyncio.timeout(8):
                        await broker.open()
                        queue = (
                            await broker.consume(await broker.audit_queue())
                            if heartbeat.document["role"] == "audit" else None
                        )
                except Exception:
                    raise QueueUnavailable() from None
                idle = IdleBackoff()
                while not stop.is_set():
                    activity = False
                    # 有积压时最多连续16条，随后让出执行；每条仍独立领取/confirm/提交。
                    for _ in range(16):
                        if stop.is_set():
                            break
                        async with asyncio.timeout(15):
                            changed = (
                                await audit_tick(engine, runtime, queue)
                                if queue else await relay_tick(engine, broker)
                            )
                        activity = changed or activity
                        heartbeat.write(
                            healthy=True, activity=changed,
                            degraded=None if broker.connection.connected.is_set() else "rabbitmq",
                        )
                        if not changed:
                            break
                    failures = 0
                    delay = idle.next(activity)
                    if queue:
                        if await queue.wait(stop, delay):
                            idle.reset()
                    elif await engine.outbox_wakeup.wait(stop, delay):
                        idle.reset()
            except QueueUnavailable:
                try:
                    await transport_scan(engine, heartbeat.document["role"])
                    heartbeat.write(healthy=True, degraded="rabbitmq")
                except Exception:
                    heartbeat.write(healthy=False)
                log("job_transport_retry", service=runtime.service, error_code="MQ_UNAVAILABLE")
            except Exception:
                heartbeat.write(healthy=False)
                log("job_retry", service=runtime.service, error_code="DEPENDENCY_UNAVAILABLE")
            finally:
                await broker.close()
                broker = None
            await pause(stop, retry_delay(failures))
            failures += 1
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
        run_managed(args.service, lambda control: run_job(args.service, args.role, control=control),
                    drain_seconds=30)
    except Exception:
        log("job_start_failed", service=args.service, error_code="INVALID_RUNTIME")
        sys.exit(1)


if __name__ == "__main__":
    main()
