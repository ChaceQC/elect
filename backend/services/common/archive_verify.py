"""恢复门禁验证冷目录完整性；有界读取，任何损坏都拒绝解除隔离。"""

from .archive_store import read
from .sql import execute


async def verify_archives(conn):
    after, count = b"", 0
    while True:
        rows = (await execute(conn, "SELECT id FROM archive_records WHERE id>:after "
            "ORDER BY id LIMIT 200", after=after)).mappings().all()
        if not rows:
            return count
        for row in rows:
            await read(conn, row["id"])
            count += 1
        after = rows[-1]["id"]


async def verify_cold_links(conn):
    # FK证明存在，逐个标识再证明其指向的载荷与索引一致。
    for table, fields in (("cold_request_keys", ("owner_user_id", "kind", "key_hash")),
                          ("cold_inbox_events", ("consumer_name", "event_id"))):
        cursor = ""
        expression = "CONCAT_WS(':'," + ",".join(
            field if field in {"kind", "consumer_name"} else f"HEX({field})"
            for field in fields) + ")"
        while True:
            rows = (await execute(conn, f"SELECT *,{expression} AS scan_cursor FROM {table} "
                f"WHERE {expression}>:cursor ORDER BY {expression} LIMIT 200",
                cursor=cursor)).mappings().all()
            if not rows:
                break
            for row in rows:
                payload = await read(conn, row["archive_id"])
                if table == "cold_inbox_events":
                    valid = all(payload[key] == row[key] for key in fields)
                else:
                    valid = (payload["owner_user_id"] == row["owner_user_id"]
                        and payload["request_digest"] == row["request_digest"]
                        and payload.get("key_hash", payload.get("idempotency_key_hash"))
                        == row["key_hash"]
                        and payload.get("run_id", payload.get("operation_id", payload.get("id")))
                        == row["result_id"])
                if not valid:
                    raise ValueError("冷标识与归档不一致")
            cursor = rows[-1]["scan_cursor"]
