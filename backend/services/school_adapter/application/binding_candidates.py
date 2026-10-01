"""绑定仅使用本人未过期的服务器候选，不接受浏览器完整学校记录。"""

from datetime import UTC, datetime
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.rooms import room_record


async def candidate(state, owner, candidate_id):
    value = await state.school_store.get_secret(f"school_adapter:candidate:{candidate_id}")
    if value and value["owner_user_id"] != str(owner):
        raise ApiError(404, ErrorCode.NOT_FOUND, "候选不存在")
    if not value or datetime.fromisoformat(value["expires_at"]) <= datetime.now(UTC):
        raise ApiError(400, ErrorCode.ROOM_CANDIDATE_EXPIRED, "候选已过期，请重新选择寝室")
    normalized = room_record(value["record"])
    if value["query"].get("room_id") != normalized["room_id"]:
        raise ApiError(400, ErrorCode.INVALID_ARGUMENT, "请先通过筛选列表核实目标寝室")
    return value


async def verify_candidate(state, principal, candidate_id):
    value = await candidate(state, principal.user_id, candidate_id)
    credential = await state.school_credentials.current(principal.user_id)
    if credential["status"] != "active" or not credential["use_allowed"]:
        raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "请先修复学校认证")
    return {
        "record": room_record(value["record"]),
        "credential_ref": str(UUID(bytes=credential["id"])),
        "credential_version": credential["version"],
    }
