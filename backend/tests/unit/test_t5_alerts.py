from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from services.common.ids import new_id
from services.monitoring.alerts import sample_is_current


@pytest.mark.parametrize(
    "change",
    [
        {"captured_at": datetime(2026, 10, 1, 9, 54, 59)},
        {"captured_at": datetime(2026, 10, 1, 10, 0, 1)},
        {"run_generation": 2},
        {"credential_version": 2},
        {"binding_id": new_id().bytes},
        {"owner_user_id": new_id().bytes},
        {"balance": None},
    ],
)
def test_stale_future_foreign_and_old_credential_samples_cannot_drive_alert(change):
    now = datetime(2026, 10, 1, 10)
    monitor = {
        "id": new_id().bytes,
        "owner_user_id": new_id().bytes,
        "binding_id": new_id().bytes,
        "generation": 1,
        "credential_version": 1,
        "desired_enabled": True,
        "state": "active",
        "credential_allowed": True,
        "credential_operation_id": None,
    }
    sample = {
        "monitor_id": monitor["id"],
        "owner_user_id": monitor["owner_user_id"],
        "binding_id": monitor["binding_id"],
        "credential_version": 1,
        "run_generation": 1,
        "captured_at": now - timedelta(minutes=5),
        "balance": Decimal("-1.00"),
    }
    assert sample_is_current(monitor, sample, now)
    assert not sample_is_current(monitor, {**sample, **change}, now)
    assert not sample_is_current({**monitor, "desired_enabled": False}, sample, now)
