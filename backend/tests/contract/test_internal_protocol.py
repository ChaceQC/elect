from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from scripts.generate_protocols import MODELS, artifacts
from services.common.events import EVENTS
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope

ROOT = Path(__file__).resolve().parents[3] / "docs/contracts"


def test_internal_schema_and_state_export_match_sources():
    for name, content in artifacts().items():
        assert (ROOT / name).read_text() == content
    for model in MODELS.values():
        assert set(model.terminal) <= model.transitions.keys()
        for state in model.terminal:
            assert not model.transitions[state]


def test_events_declare_ownership_dedupe_and_no_sensitive_payload():
    manifest = yaml.safe_load((ROOT / "events/registry.yaml").read_text())
    forbidden = set(manifest["transport"]["forbidden_payload"])
    for event in manifest["events"]:
        assert event["producer"] and event["consumers"]
        assert event["aggregate_version"] and event["dedupe_key"]
        assert event["schema_version"] == 1
        assert not forbidden.intersection(event["required_payload"])
        payload_type, producers = EVENTS[event["type"]]
        required = {
            name for name, field in payload_type.model_fields.items() if field.is_required()
        }
        assert required == set(event["required_payload"])
        assert not forbidden.intersection(payload_type.model_fields)
        assert set(
            event["producer"] if isinstance(event["producer"], list) else [event["producer"]]
        ) == set(producers)


def test_event_rejects_sensitive_payload_and_wrong_producer():
    value = {
        "event_id": new_id(),
        "type": "monitor.run_ready",
        "schema_version": 1,
        "producer": "monitoring",
        "aggregate_id": new_id(),
        "aggregate_version": 1,
        "occurred_at": "2026-10-01T10:00:00+08:00",
        "request_id": new_id(),
        "payload": {"run_id": str(new_id()), "generation": 1},
        "dedupe_key": "fixture",
    }
    EventEnvelope.model_validate(value)
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate({**value, "producer": "payment"})
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(
            {**value, "payload": {**value["payload"], "token": "fixture-secret"}}
        )
