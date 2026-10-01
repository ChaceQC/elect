"""Room 写操作统一先锁本人偏好；不持数据库锁调用其他服务。"""

from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first


def require_no_removal(preference):
    if preference["removal_operation_id"]:
        raise ApiError(
            409,
            ErrorCode.OPERATION_IN_PROGRESS,
            "学校解绑仍在确认，请等待原操作",
            existing_operation_id=UUID(bytes=preference["removal_operation_id"]),
        )


async def lock_preference(conn, owner):
    await execute(
        conn,
        "INSERT INTO room_preferences (owner_user_id,version,state) VALUES (:owner,1,'ready') "
        "ON DUPLICATE KEY UPDATE owner_user_id=owner_user_id",
        owner=owner.bytes if hasattr(owner, "bytes") else owner,
    )
    return await first(
        conn,
        "SELECT * FROM room_preferences WHERE owner_user_id=:owner FOR UPDATE",
        owner=owner.bytes if hasattr(owner, "bytes") else owner,
    )


async def locked_operation(conn, row):
    await lock_preference(conn, row["owner_user_id"])
    return await first(
        conn,
        "SELECT * FROM room_operations WHERE id=:id AND lease_owner=:lease "
        "AND lease_until>UTC_TIMESTAMP(6) FOR UPDATE",
        id=row["id"],
        lease=row["lease_owner"],
    )
