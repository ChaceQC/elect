import os
from datetime import datetime, timedelta

import pytest

from services.common.ids import new_id
from services.monitoring.configuration import validate_config
from services.monitoring.email_crypto import EmailCrypto
from services.monitoring.fences import Execution, valid_execution


def test_email_ciphertext_binds_owner_version_and_supports_key_rotation():
    owner = new_id()
    old = EmailCrypto("v1", {"v1": os.urandom(32)})
    encrypted = old.seal("student@example.invalid", owner, 1)
    assert b"student@example.invalid" not in encrypted
    rotated = EmailCrypto("v2", {**old.keys, "v2": os.urandom(32)})
    assert rotated.open(encrypted, owner, 1) == "student@example.invalid"
    for other, version in [(new_id(), 1), (owner, 2)]:
        with pytest.raises(RuntimeError, match="邮箱无法解密"):
            rotated.open(encrypted, other, version)
    with pytest.raises(RuntimeError, match="邮箱无法解密"):
        rotated.open(encrypted[:-2] + b"xx", owner, 1)


@pytest.mark.parametrize("email", ["a@b", "a b@example.org", "a@b@example.org", "a@example.org\n"])
def test_enabled_monitor_requires_usable_email(email):
    from services.common.http import ApiError

    with pytest.raises(ApiError) as error:
        validate_config({"enabled": True, "email": email}, {})
    assert error.value.status == 422


def test_fence_requires_active_run_pointer_and_current_authorization():
    monitor, run_id, binding = new_id(), new_id(), new_id()
    now = datetime(2026, 10, 1)
    execution = Execution(monitor, run_id, 1, binding, 1, 1, "worker")
    state = {
        "id": monitor.bytes,
        "active_run_id": run_id.bytes,
        "generation": 1,
        "binding_id": binding.bytes,
        "credential_version": 1,
        "desired_enabled": True,
        "credential_allowed": True,
        "credential_operation_id": None,
        "state": "active",
    }
    run = {
        "id": run_id.bytes,
        "monitor_id": monitor.bytes,
        "state": "running",
        "generation": 1,
        "binding_id": binding.bytes,
        "credential_version": 1,
        "execution_epoch": 1,
        "lease_owner": "worker",
        "lease_until": now + timedelta(seconds=1),
        "cancel_requested_at": None,
    }
    assert valid_execution(state, run, execution, now)
    for change in [
        {"active_run_id": new_id().bytes},
        {"credential_allowed": False},
        {"credential_operation_id": new_id().bytes},
        {"desired_enabled": False},
        {"state": "retargeting"},
    ]:
        assert not valid_execution({**state, **change}, run, execution, now)
    assert not valid_execution(state, run, execution, now + timedelta(seconds=1))
