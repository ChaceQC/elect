"""保留期限及共享传输台账归档；领域调用只接收本库连接。"""

from datetime import timedelta

from . import archive_store
from .retention_cursor import scan
from .sql import execute, first

TERMINAL = "('succeeded','failed','cancelled')"


async def cutoff_time(conn, cutoff):
    now = (await first(conn, "SELECT UTC_TIMESTAMP(6) AS now"))["now"]
    return min(cutoff, now - timedelta(days=180))


async def archive_transport(conn, kind, cutoff, *, apply=False, limit=200, after=""):
    if kind not in {"inbox_events", "outbox_events"}:
        raise ValueError("未登记归档类别")
    boundary = await cutoff_time(conn, cutoff)
    condition = ("processed_at<=:cutoff" if kind == "inbox_events" else
                 "published_at<=:cutoff AND publish_lease_owner IS NULL")
    columns = ("consumer_name", "event_id") if kind == "inbox_events" else ("event_id",)
    where, order, cursor_params = scan(columns, after, text_first=kind == "inbox_events")
    rows = (await execute(conn, f"SELECT * FROM {kind} WHERE {condition} "
        f"AND created_at<=:cutoff AND {where} ORDER BY {order} LIMIT :limit "
        "FOR UPDATE SKIP LOCKED", cutoff=boundary, limit=limit, **cursor_params)).mappings().all()
    if apply:
        for row in rows:
            key = row["event_id"].hex()
            if kind == "inbox_events":
                key = row["consumer_name"] + ":" + key
                cold = await first(conn, "SELECT archive_id FROM cold_inbox_events "
                    "WHERE consumer_name=:consumer AND event_id=:event",
                    consumer=row["consumer_name"], event=row["event_id"])
                if cold:
                    original = await archive_store.read(conn, cold["archive_id"])
                    if any(original[field] != row[field] for field in columns):
                        raise archive_store.unavailable()
                    await execute(conn, "DELETE FROM inbox_events WHERE consumer_name=:consumer "
                        "AND event_id=:id", consumer=row["consumer_name"], id=row["event_id"])
                    continue
            archive = await archive_store.save(conn, kind, key, row)
            if kind == "inbox_events":
                await execute(conn, "INSERT INTO cold_inbox_events "
                    "(consumer_name,event_id,processed_at,archive_id) VALUES "
                    "(:consumer,:event,:processed,:archive)", consumer=row["consumer_name"],
                    event=row["event_id"], processed=row["processed_at"], archive=archive)
                await execute(conn, "DELETE FROM inbox_events WHERE consumer_name=:consumer "
                              "AND event_id=:id", consumer=row["consumer_name"], id=row["event_id"])
            else:
                await execute(conn, "DELETE FROM outbox_events WHERE event_id=:id",
                              id=row["event_id"])
    cursor = after
    if rows:
        cursor = rows[-1]["event_id"].hex().upper()
        if kind == "inbox_events":
            cursor = rows[-1]["consumer_name"] + ":" + cursor
    return {"candidates": len(rows), "archived": len(rows) if apply else 0,
            "retained": 0, "cursor": cursor}


async def foreign_references(conn, table, row):
    """只读取本库实际外键；未知约束保守拒绝移除，不关闭FOREIGN_KEY_CHECKS。"""
    refs = (await execute(conn, "SELECT TABLE_NAME AS child,COLUMN_NAME AS col,"
        "REFERENCED_COLUMN_NAME AS parent FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE REFERENCED_TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME=:table",
        table=table)).mappings().all()
    for ref in refs:
        if any(not value.replace("_", "").isalnum() for value in ref.values()):
            raise ValueError("外键标识不受支持")
        if await first(conn, f"SELECT 1 FROM `{ref['child']}` WHERE `{ref['col']}`=:value LIMIT 1",
                       value=row[ref["parent"]]):
            return True
    return False
