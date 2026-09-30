"""仅保存经过登记、签名与 DTO 校验的脱敏审计字段。"""

from datetime import UTC

from sqlalchemy import text


async def record_audit(connection, event):
    payload = event.payload
    await connection.execute(
        text(
            "INSERT INTO audit_events (event_id,actor_user_id,service,action,object_type,object_id,"
            "result,request_id,occurred_at,sanitized_details) VALUES (:id,:actor,:service,:action,"
            ":object_type,:object_id,:result,:request_id,:occurred,'{}')"
        ),
        {
            "id": event.event_id.bytes,
            "actor": payload.actor_user_id.bytes if payload.actor_user_id else None,
            "service": event.producer,
            "action": payload.action,
            "object_type": payload.object_type,
            "object_id": payload.object_id.bytes,
            "result": payload.result,
            "request_id": event.request_id.bytes,
            "occurred": event.occurred_at.astimezone(UTC).replace(tzinfo=None),
        },
    )
