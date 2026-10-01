from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal

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
