import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from cryptography.exceptions import InvalidSignature

from services.common.broker import signed_message, verified_event
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope


def audit_event():
    return EventEnvelope(
        event_id=new_id(),
        type="audit.recorded",
        schema_version=1,
        producer="identity",
        aggregate_id=new_id(),
        aggregate_version=1,
        occurred_at=datetime.now(UTC),
        request_id=new_id(),
        payload={
            "action": "foundation.smoke",
            "object_type": "fixture",
            "object_id": new_id(),
            "result": "succeeded",
        },
        dedupe_key="test",
    )


def test_signed_events_reject_tampering_and_sensitive_fields(runtime_factory):
    runtime = runtime_factory("identity")
    runtime.trust_bundle[runtime.key_id].scopes.append("event:audit")
    message = signed_message(runtime, audit_event())
    assert verified_event(runtime, message).producer == "identity"
    data = json.loads(message.body)
    data["payload"]["token"] = "synthetic-sensitive"
    tampered = SimpleNamespace(
        headers=message.headers, body=json.dumps(data).encode(), message_id=message.message_id
    )
    with pytest.raises(InvalidSignature):
        verified_event(runtime, tampered)
    with pytest.raises(ValueError):
        signed_message(runtime_factory("room"), audit_event())
    with pytest.raises(ValueError):
        EventEnvelope.model_validate(data)
