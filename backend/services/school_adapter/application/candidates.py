import secrets
from datetime import UTC, datetime, timedelta

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id

from ..infrastructure.rooms import room_record


async def search_candidates(state, principal, command):
    await state.school_store.rate("search", str(principal.user_id), limit=1, window=1)
    value = await state.school_sessions.read(
        principal.user_id,
        principal.request_id,
        "/base/rooms/queryRoomList",
        {
            "size": command.page_size,
            "current": command.page,
            "pageTotal": 100,
            "searchValue": command.q,
            "roomId": command.room_id or "",
        },
    )
    page = value.get("data")
    if not isinstance(page, dict) or not isinstance(page.get("records"), list):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校候选分页结构异常")
    records, total = page["records"], page.get("total")
    if type(total) is not int or total < 0 or len(records) > command.page_size:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校候选分页字段异常")
    expires, query_id = datetime.now(UTC) + timedelta(minutes=5), str(new_id())
    items = []
    for raw in records:
        record = room_record(raw)
        candidate_id = secrets.token_urlsafe(32)
        await state.school_store.put_secret(
            f"school_adapter:candidate:{candidate_id}",
            {
                "owner_user_id": str(principal.user_id),
                "query_id": query_id,
                "query": command.model_dump(),
                "expires_at": expires.isoformat(),
                "record": raw,
            },
            ttl=300,
        )
        items.append(
            {
                "candidate_id": candidate_id,
                "room_id": record["room_id"],
                "building": record["building"],
                "number": record["number"],
                "display_name": record["display_name"],
                "already_bound": False,
                "expires_at": expires,
            }
        )
    return {
        "items": items,
        "page": command.page,
        "page_size": command.page_size,
        "total": total,
        "search_quality": "unverified",
        "expires_at": expires,
    }
