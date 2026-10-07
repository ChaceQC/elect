import asyncio
from contextlib import nullcontext
from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.read_schedule import ReadSchedule, processing
from services.common.security import Principal

from .binding_saga import BindingSaga
from .control_jobs import claim, update
from .default_saga import DefaultSaga
from .removal_saga import RemovalSaga
from .repository import RoomRepository


async def sync_tick(app, *, schedule=None, stop=None, heartbeat=None):
    with heartbeat.work(110) if heartbeat else nullcontext():
        async with asyncio.timeout(110):
            return await sync_once(app, schedule=schedule, stop=stop)


async def sync_once(app, *, schedule=None, stop=None):
    repository = RoomRepository(app.state.database)
    operation = await repository.claim(schedule, stop=stop)
    if operation is None:
        return False
    request_id = new_id()
    principal = Principal("room", UUID(bytes=operation["owner_user_id"]), 1, request_id)
    observation = None
    try:
        value = await app.state.service_client.call(
            "school_adapter", "/rooms/bound", "school:rooms", request_id, principal=principal
        )
        observation = value.get("observation")
        records, error = value["items"], observation.get("error_code") if observation else None
    except ApiError as failure:
        records, error = [], failure.code
    await repository.complete(operation, records, error, request_id, observation)
    return True


async def control_tick(app):
    row = await claim(app.state.database)
    if row is None:
        return False
    principal = Principal("room", UUID(bytes=row["owner_user_id"]), 1, new_id())
    try:
        saga = {
            "bind_room": BindingSaga,
            "switch_default": DefaultSaga,
            "unbind_room": RemovalSaga,
        }[row["type"]]
        await saga(app.state.database, app.state.service_client).advance(row, principal)
    except ApiError as error:
        await update(app.state.database, row, error=error.code, state="reconciling", release=True,
                     delay=30 if row["type"] == "unbind_room" else 5)
    return True


async def room_tick(app, *, stop=None, hub=None, heartbeat=None):
    from .query_worker import history_tick, refresh_tick

    if stop and stop.is_set():
        return False
    if not hasattr(app.state, "read_schedule"):
        app.state.read_schedule = ReadSchedule(("binding_sync", "balance_refresh", "history_sync"))
        app.state.read_wakeup_lock = asyncio.Lock()
    schedule = app.state.read_schedule
    for kind in schedule.order():
        if stop and stop.is_set():
            return False
        tick = {"binding_sync": sync_tick, "balance_refresh": refresh_tick,
                "history_sync": history_tick}[kind]
        with processing("room", kind):
            if await tick(app, schedule=schedule, stop=stop, heartbeat=heartbeat):
                return True
    from .wakeups import drain

    # MQ只是提示；只有空闲槽且共享channel未被使用时才读取，不让忙槽等待它。
    lock = app.state.read_wakeup_lock
    if (not stop or not stop.is_set()) and not lock.locked():
        async with lock:
            await drain(app, hub=hub)
    return False
