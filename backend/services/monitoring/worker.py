"""余额读取在事务之外；续租失败取消 HTTP 且拒绝提交。"""

import asyncio

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import first

from .execution import claim_run, renew
from .recovery import acknowledge_cancel
from .results import fail, succeed


async def collect(app, execution, request_id):
    async with app.state.database.connect() as conn:
        monitor = await first(
            conn, "SELECT owner_user_id FROM monitors WHERE id=:id", id=execution.monitor_id.bytes
        )
    from uuid import UUID

    principal = Principal("monitoring", UUID(bytes=monitor["owner_user_id"]), 1, request_id)
    return await app.state.service_client.call(
        "school_adapter",
        "/queries/collect",
        "school:collect",
        request_id,
        {"binding_id": str(execution.binding_id)},
        principal=principal,
    )


async def execute_run(app, execution, heartbeat=None):
    request_id = new_id()
    task = asyncio.create_task(collect(app, execution, request_id))
    try:
        async with asyncio.timeout(90):
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=10)
                if not done and not await renew(app.state.database, execution):
                    task.cancel()
                    await acknowledge_cancel(app.state.database, execution)
                    return False
                if not done and heartbeat:
                    heartbeat.write(healthy=True)
            value = task.result()
            await succeed(
                app.state.database, execution, value["balance"], request_id,
                meter=value.get("meter"),
            )
        return True
    except TimeoutError:
        await finish_failure(app, execution, ErrorCode.SCHOOL_TIMEOUT, True, request_id)
    except ApiError as error:
        if error.code == ErrorCode.VERSION_CONFLICT:
            await acknowledge_cancel(app.state.database, execution)
        else:
            await finish_failure(
                app, execution, error.code, error.retryable, request_id, error.retry_after_seconds
            )
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return False


async def finish_failure(app, execution, code, retryable, request_id, retry_after=None):
    try:
        await fail(app.state.database, execution, code, retryable, request_id, retry_after)
    except ApiError as error:
        if error.code != ErrorCode.VERSION_CONFLICT:
            raise
        await acknowledge_cancel(app.state.database, execution)


async def worker_tick(app, run_id=None, heartbeat=None):
    execution = await claim_run(app.state.database, run_id)
    if not execution:
        return False
    if heartbeat:
        heartbeat.write(healthy=True)
    await execute_run(app, execution, heartbeat)
    return True
