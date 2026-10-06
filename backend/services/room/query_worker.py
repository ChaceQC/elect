"""持久余额与历史读取；领取事务在调用学校前结束。"""

import asyncio
from contextlib import nullcontext
from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal

from .balance import claim_refresh, finish_refresh
from .history_execution import execute_window
from .history_jobs import claim_history


async def refresh_tick(app, *, schedule=None, stop=None, heartbeat=None):
    with heartbeat.work(45) if heartbeat else nullcontext():
        async with asyncio.timeout(45):
            return await refresh_once(app, schedule=schedule, stop=stop)


async def refresh_once(app, *, schedule=None, stop=None):
    from .balance_store import settle_aliases

    settled = await settle_aliases(app.state.database)
    row = await claim_refresh(app.state.database, schedule, stop=stop)
    if row:
        principal = Principal("room", UUID(bytes=row["owner_user_id"]), 1, new_id())
        observation = None
        try:
            value = await app.state.service_client.call(
                "school_adapter",
                "/rooms/bound",
                "school:rooms",
                principal.request_id,
                principal=principal,
            )
            observation = value.get("observation")
            records, error = value["items"], observation.get("error_code") if observation else None
        except ApiError as failure:
            records, error = [], failure.code
        await finish_refresh(app.state.database, row, records, error, observation)
    return bool(row or settled)


async def query_tick(app, *, stop=None, heartbeat=None):
    row = await refresh_tick(app, stop=stop, heartbeat=heartbeat)
    if stop and stop.is_set():
        return bool(row)
    history = await history_tick(app, stop=stop, heartbeat=heartbeat)
    return bool(row or history)


async def history_tick(app, *, schedule=None, stop=None, heartbeat=None):
    history = await claim_history(app.state.database, schedule, stop=stop)
    if history:
        await execute_window(app, history, heartbeat=heartbeat)
    return bool(history)
