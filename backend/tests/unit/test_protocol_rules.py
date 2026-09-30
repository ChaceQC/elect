import pytest
from pydantic import ValidationError

from services.common.dto import DateRange, Meta
from services.common.ids import decode_id, encode_id, new_id
from services.identity.states import LOGIN_ATTEMPT
from services.monitoring.dto import MonitorPatch
from services.monitoring.states import RUN
from services.notification.states import JOB
from services.payment.dto import OrderRequest
from services.payment.states import ORDER
from services.room.states import ROOM_OPERATION


@pytest.mark.parametrize("interval", [60, 75, 1440])
def test_interval_integer_boundaries(interval):
    assert MonitorPatch(expected_version=1, interval_minutes=interval).interval_minutes == interval


@pytest.mark.parametrize("interval", [59, 1441, 60.5, True, "60"])
def test_invalid_interval_cannot_be_coerced(interval):
    with pytest.raises(ValidationError):
        MonitorPatch(expected_version=1, interval_minutes=interval)


@pytest.mark.parametrize("amount", [20.0, "NaN", "Infinity", "1e2", "20.001", "0.00"])
def test_order_requires_positive_exact_decimal_string(amount):
    with pytest.raises(ValidationError):
        OrderRequest(binding_id=new_id(), amount=amount)


def test_patch_disable_needs_no_other_draft_fields():
    patch = MonitorPatch(expected_version=1, enabled=False)
    assert patch.model_fields_set == {"expected_version", "enabled"}
    assert patch.enabled is False
    with pytest.raises(ValidationError):
        MonitorPatch(enabled=False)
    with pytest.raises(ValidationError):
        MonitorPatch(expected_version=1, enabled=None)
    with pytest.raises(ValidationError):
        MonitorPatch(expected_version=1, threshold="10000.01")


def test_date_range_inclusive_and_timestamps_require_timezone():
    DateRange(start_date="2026-01-01", end_date="2027-01-01")
    with pytest.raises(ValidationError):
        DateRange(start_date="2026-01-01", end_date="2027-01-02")
    with pytest.raises(ValidationError):
        DateRange(start_date="2026-10-02", end_date="2026-10-01")
    with pytest.raises(ValidationError):
        Meta(request_id=new_id(), server_time="2026-10-01T00:00:00")


def test_uuid7_binary_roundtrip():
    identifier = new_id()
    assert identifier.version == 7
    assert len(encode_id(identifier)) == 16
    assert decode_id(encode_id(identifier)) == identifier


@pytest.mark.parametrize(
    "model,before,after",
    [
        (LOGIN_ATTEMPT, "staged", "session_issued"),
        (RUN, "cancel_requested", "succeeded"),
        (RUN, "succeeded", "running"),
        (ROOM_OPERATION, "unknown", "running"),
        (ORDER, "submit_unknown", "submitting"),
        (ORDER, "awaiting_payment", "submitting"),
        (JOB, "delivery_unknown", "sending"),
    ],
)
def test_unknown_cancel_and_terminal_states_cannot_repeat_effects(model, before, after):
    with pytest.raises(ValueError):
        model.require(before, after)


def test_confirmed_reconciliation_and_cancel_can_finish():
    ORDER.require("submit_unknown", "awaiting_payment")
    ROOM_OPERATION.require("unknown", "reconciling")
    RUN.require("cancel_requested", "cancelled")
