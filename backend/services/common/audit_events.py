from datetime import UTC, datetime

from .events import AuditPayload
from .ids import new_id
from .internal_dto import EventEnvelope
from .outbox import append_event


async def record_audit(
    connection,
    producer,
    action,
    object_type,
    object_id,
    request_id,
    *,
    actor=None,
    result="succeeded",
    version=1,
):
    event_id = new_id()
    await append_event(
        connection,
        EventEnvelope(
            event_id=event_id,
            type="audit.recorded",
            schema_version=1,
            producer=producer,
            aggregate_id=object_id,
            aggregate_version=version,
            occurred_at=datetime.now(UTC),
            request_id=request_id,
            dedupe_key=str(event_id),
            payload=AuditPayload(
                action=action,
                object_type=object_type,
                object_id=object_id,
                result=result,
                actor_user_id=actor,
            ),
        ),
    )
