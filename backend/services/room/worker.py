from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal

from .binding_saga import BindingSaga
from .control_jobs import claim, update
from .default_saga import DefaultSaga
from .removal_saga import RemovalSaga
from .repository import RoomRepository


async def sync_tick(app):
    repository = RoomRepository(app.state.database)
    operation = await repository.claim()
    if operation is None:
        return False
    request_id = new_id()
    principal = Principal("room", UUID(bytes=operation["owner_user_id"]), 1, request_id)
    try:
        value = await app.state.service_client.call(
            "school_adapter", "/rooms/bound", "school:rooms", request_id, principal=principal
        )
        records, error = value["items"], None
    except ApiError as failure:
        records, error = [], failure.code
    await repository.complete(operation, records, error, request_id)
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
        await update(app.state.database, row, error=error.code, state="reconciling", release=True)
    return True


async def room_tick(app):
    from .query_worker import query_tick

    controls = await control_tick(app)
    synced = await sync_tick(app)
    queried = await query_tick(app)
    from .wakeups import drain

    await drain(app)
    return controls or synced or queried
