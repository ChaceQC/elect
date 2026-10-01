"""Room 写操作统一先锁本人偏好；不持数据库锁调用其他服务。"""

from services.common.sql import execute, first


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
