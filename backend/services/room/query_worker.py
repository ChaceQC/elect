"""持久余额与历史读取；领取事务在调用学校前结束。"""

from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal

from .balance import claim_refresh, finish_refresh
from .history_jobs import claim_history
from .history_store import finish_history


async def query_tick(app):
    row = await claim_refresh(app.state.database)
    if row:
        principal = Principal("room", UUID(bytes=row["owner_user_id"]), 1, new_id())
        try:
            value = await app.state.service_client.call(
                "school_adapter",
                "/rooms/bound",
                "school:rooms",
                principal.request_id,
                principal=principal,
            )
            records, error = value["items"], None
        except ApiError as failure:
            records, error = [], failure.code
        await finish_refresh(app.state.database, row, records, error)
    history = await claim_history(app.state.database)
    if history:
        principal = Principal("room", UUID(bytes=history["owner_user_id"]), 1, new_id())
        try:
            value = await app.state.service_client.call(
                "school_adapter",
                "/queries/history",
                "school:history",
                principal.request_id,
                {
                    "binding_id": str(UUID(bytes=history["binding_id"])),
                    "start_date": history["start_date"].isoformat(),
                    "end_date": history["end_date"].isoformat(),
                },
                principal=principal,
            )
            error, retryable, retry_after = None, False, None
        except ApiError as failure:
            value, error, retryable = None, failure.code, failure.retryable
            retry_after = failure.retry_after_seconds
        await finish_history(app.state.database, history, value, error, retryable, retry_after)
    return bool(row or history)
