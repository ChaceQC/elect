"""将已确认的 B02 记录写入本人镜像；候选记录不能创建 active binding。"""

from services.common.ids import new_id
from services.common.sql import execute, first


async def upsert_room(conn, record):
    await execute(
        conn,
        "INSERT INTO rooms (id,school_id,school_room_id,building_name,room_no,meter_code,"
        "metadata_version) VALUES (:id,'hbue',:school,:building,:number,:meter,1) "
        "ON DUPLICATE KEY UPDATE building_name=:building,room_no=:number,meter_code=:meter,"
        "updated_at=UTC_TIMESTAMP(6)",
        id=new_id().bytes,
        school=record["room_id"],
        building=record["building"],
        number=record["number"],
        meter=record.get("meter_code"),
    )
    return await first(
        conn,
        "SELECT id FROM rooms WHERE school_id='hbue' AND school_room_id=:id",
        id=record["room_id"],
    )


async def confirm_binding(conn, owner, record):
    room = await upsert_room(conn, record)
    await execute(
        conn,
        "INSERT INTO room_bindings (id,owner_user_id,room_id,school_relation_id,status,"
        "last_confirmed_at) VALUES (:id,:owner,:room,:relation,'active',UTC_TIMESTAMP(6)) "
        "ON DUPLICATE KEY UPDATE status='active',school_relation_id=:relation,"
        "last_confirmed_at=UTC_TIMESTAMP(6),updated_at=UTC_TIMESTAMP(6)",
        id=new_id().bytes,
        owner=owner,
        room=room["id"],
        relation=record.get("relation_id"),
    )
    binding = await first(
        conn,
        "SELECT id FROM room_bindings WHERE owner_user_id=:owner AND status<>'inactive' AND "
        "room_id=:room",
        owner=owner,
        room=room["id"],
    )
    await execute(
        conn,
        "INSERT INTO room_balance_cache (binding_id,balance,fetched_at,source,quality) "
        "VALUES (:id,:balance,UTC_TIMESTAMP(6),'school_bound_rooms','fresh') "
        "ON DUPLICATE KEY UPDATE balance=:balance,fetched_at=UTC_TIMESTAMP(6),"
        "quality='fresh',error_code=NULL,updated_at=UTC_TIMESTAMP(6)",
        id=binding["id"],
        balance=record["balance"],
    )
    return binding["id"]


async def mirror_bindings(conn, owner, records):
    previous = (
        (
            await execute(
                conn,
                "SELECT id FROM room_bindings WHERE owner_user_id=:owner AND status<>'inactive'",
                owner=owner,
            )
        )
        .scalars()
        .all()
    )
    seen = {await confirm_binding(conn, owner, record) for record in records}
    missing = [binding for binding in previous if binding not in seen]
    for binding in missing:
        await execute(
            conn,
            "UPDATE room_bindings SET status='rechecking',updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=binding,
        )
        await execute(
            conn,
            "UPDATE room_balance_cache SET quality='stale',updated_at=UTC_TIMESTAMP(6) WHERE "
            "binding_id=:id",
            id=binding,
        )
    return "stale" if missing else "ready" if records else "empty"
