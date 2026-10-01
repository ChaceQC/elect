"""学校楼栋/楼层/房间三级列表；关键词由浏览器在当前列表内过滤。"""

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.room.dto import FilterChoices

from ..infrastructure.rooms import opaque_id, text_field


async def filter_choices(state, principal, command):
    await state.school_store.rate("filter", str(principal.user_id), limit=3, window=1)
    paths = {
        "buildings": "/base/baseBuildings/getBuildList",
        "floors": "/base/rooms/getAllFoolNumByBuildId",
        "rooms": "/base/rooms/getRoomListByBuildIdAndFloor",
    }
    params = {"searchValue": ""}
    if command.level == "buildings":
        params.update(size=999, current=1)
    else:
        params["buildingId"] = command.building_id
    if command.level == "rooms":
        params["floorNum"] = command.floor
    value = await state.school_sessions.read(
        principal.user_id, principal.request_id, paths[command.level], params
    )
    rows = value.get("data")
    if command.level == "buildings":
        if not isinstance(rows, dict) or type(rows.get("total")) is not int:
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校楼栋分页异常")
        if rows["total"] > 999 or rows["total"] != len(rows.get("records", [])):
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校楼栋列表不完整")
        rows = rows.get("records")
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校筛选列表异常")
    items = []
    for row in rows:
        if not isinstance(row, dict):
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校筛选项异常")
        identifier = opaque_id(row.get("value"))
        if command.level == "floors":
            identifier = identifier.split("-", 1)[0]
        label = text_field(row.get("label"), 128)
        if not label or any(item["id"] == identifier for item in items):
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校筛选项缺失或重复")
        items.append({"id": identifier, "label": label})
    return FilterChoices(items=items)
