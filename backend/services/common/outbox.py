"""可靠传输表的事务操作；连接由所属域传入，不访问业务表。"""

import json
import random

from sqlalchemy import text

from .ids import new_id
from .internal_dto import EventEnvelope


async def append_event(connection, event: EventEnvelope):
    await connection.execute(
        text(
            "INSERT INTO outbox_events (event_id,type,schema_version,aggregate_id,"
            "aggregate_version,"
            "payload,available_at,publish_attempts) VALUES (:id,:type,:schema,:aggregate,:version,"
            ":payload,UTC_TIMESTAMP(6),0)"
        ),
        {
            "id": event.event_id.bytes,
            "type": event.type,
            "schema": event.schema_version,
            "aggregate": event.aggregate_id.bytes,
            "version": event.aggregate_version,
            "payload": event.model_dump_json(),
        },
    )


async def claim_event(engine, lease_seconds=30):
    owner = str(new_id())
    async with engine.begin() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT event_id,payload,publish_attempts FROM outbox_events "
                        "WHERE published_at IS NULL AND available_at <= UTC_TIMESTAMP(6) "
                        "AND (publish_lease_until IS NULL OR "
                        "publish_lease_until <= UTC_TIMESTAMP(6)) "
                        "ORDER BY available_at,event_id LIMIT 1 FOR UPDATE SKIP LOCKED"
                    )
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        await connection.execute(
            text(
                "UPDATE outbox_events SET publish_lease_owner=:owner,"
                "publish_lease_until=DATE_ADD(UTC_TIMESTAMP(6), INTERVAL :seconds SECOND),"
                "publish_attempts=publish_attempts+1,updated_at=UTC_TIMESTAMP(6) WHERE event_id=:id"
            ),
            {"owner": owner, "seconds": lease_seconds, "id": row["event_id"]},
        )
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return {
            "event_id": row["event_id"],
            "owner": owner,
            "payload": payload,
            "attempt": row["publish_attempts"] + 1,
        }


async def finish_event(engine, claim, *, published):
    delay = min(300, 2 ** min(claim["attempt"], 8)) + random.uniform(0, 1)
    if published:
        update = "published_at=UTC_TIMESTAMP(6)"
    else:
        update = "available_at=DATE_ADD(UTC_TIMESTAMP(6), INTERVAL :delay MICROSECOND)"
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                f"UPDATE outbox_events SET {update},publish_lease_owner=NULL,"
                "publish_lease_until=NULL,"
                "updated_at=UTC_TIMESTAMP(6) WHERE event_id=:id AND publish_lease_owner=:owner "
                "AND publish_lease_until > UTC_TIMESTAMP(6) AND published_at IS NULL"
            ),
            {"id": claim["event_id"], "owner": claim["owner"], "delay": int(delay * 1_000_000)},
        )
        return result.rowcount == 1


async def consume_once(engine, consumer_name, event, handler):
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "INSERT IGNORE INTO inbox_events (consumer_name,event_id,processed_at) "
                "VALUES (:consumer,:event,UTC_TIMESTAMP(6))"
            ),
            {"consumer": consumer_name, "event": event.event_id.bytes},
        )
        if result.rowcount == 0:
            return False
        await handler(connection, event)
        return True
