import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from services.common.ids import new_id
from services.monitoring import alerts, permits

NOW = datetime(2026, 10, 14, 12)


class _Transaction:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


async def _exercise_paths(monkeypatch, interval, authorized_age, sent_age, in_flight):
    monitor_id, owner_id, binding_id = new_id().bytes, new_id().bytes, new_id().bytes
    episode_id, slot_id, sample_id = new_id().bytes, new_id().bytes, new_id().bytes
    job_id = new_id()
    authorized_at = NOW - authorized_age if authorized_age is not None else None
    last_email_sent_at = NOW - sent_age if sent_age is not None else None
    monitor = {
        "id": monitor_id,
        "owner_user_id": owner_id,
        "binding_id": binding_id,
        "state": "active",
        "desired_enabled": True,
        "credential_allowed": True,
        "credential_operation_id": None,
        "generation": 1,
        "credential_version": 1,
        "email_version": 1,
        "current_episode_id": episode_id,
        "interval_minutes": interval,
        "repeat_limit": 3,
        "threshold": Decimal("10.00"),
        "last_sample_id": sample_id,
        "last_email_sent_at": last_email_sent_at,
    }
    episode = {
        "id": episode_id,
        "monitor_id": monitor_id,
        "state": "open",
        "generation": 1,
        "binding_id": binding_id,
    }
    slot = {
        "id": slot_id,
        "episode_id": episode_id,
        "sample_id": sample_id,
        "state": "reserved",
        "generation": 1,
        "email_version": 1,
        "ordinal": 1,
        "delivery_id": None,
    }
    sample = {
        "id": sample_id,
        "monitor_id": monitor_id,
        "owner_user_id": owner_id,
        "binding_id": binding_id,
        "credential_version": 1,
        "run_generation": 1,
        "captured_at": NOW - timedelta(minutes=1),
        "balance": Decimal("5.00"),
    }
    history = {"at": authorized_at, "in_flight": int(in_flight)}

    monkeypatch.setattr(alerts, "first", AsyncMock(return_value=history))
    monkeypatch.setattr(permits, "lock_monitor", AsyncMock(return_value=monitor))

    async def read_permit_row(conn, statement, **params):
        if "FROM alert_episodes e JOIN alert_slots" in statement:
            return episode
        if "FROM alert_slots WHERE id=:id FOR UPDATE" in statement:
            return slot
        if "UTC_TIMESTAMP(6) AS now" in statement:
            return {"now": NOW}
        if "FROM send_permits" in statement:
            return None
        if "FROM monitor_samples s" in statement:
            return sample
        if "MAX(s.authorized_at)" in statement:
            return history
        raise AssertionError(f"Unexpected query: {statement}")

    monkeypatch.setattr(permits, "first", AsyncMock(side_effect=read_permit_row))
    monkeypatch.setattr(permits, "execute", AsyncMock())

    class _Engine:
        def begin(self):
            return _Transaction()

    command = SimpleNamespace(
        owner_user_id=UUID(bytes=owner_id),
        alert_slot_id=UUID(bytes=slot_id),
        generation=1,
        email_version=1,
        job_id=job_id,
        execution_epoch=1,
    )
    creation_blocked = await alerts.cooldown(object(), monitor, NOW)
    send_permit = await permits.authorize(_Engine(), command)
    return creation_blocked, send_permit


@pytest.mark.parametrize(
    "interval, authorized_age, sent_age, in_flight, blocked, denial",
    [
        pytest.param(
            60,
            timedelta(minutes=57, seconds=59),
            timedelta(minutes=58, seconds=30),
            False,
            True,
            "COOLDOWN",
            id="60m-authorized-at-57m59s-blocks",
        ),
        pytest.param(
            60,
            timedelta(minutes=58, seconds=30),
            timedelta(minutes=58),
            False,
            False,
            None,
            id="60m-sent-at-58m-allows",
        ),
        pytest.param(
            60,
            timedelta(minutes=59),
            timedelta(minutes=58, seconds=30),
            False,
            False,
            None,
            id="60m-sent-at-58m30s-allows",
        ),
        pytest.param(
            1440,
            timedelta(minutes=1437, seconds=59),
            timedelta(minutes=1438, seconds=30),
            False,
            True,
            "COOLDOWN",
            id="1440m-authorized-at-1437m59s-blocks",
        ),
        pytest.param(
            1440,
            timedelta(minutes=1438, seconds=30),
            timedelta(minutes=1438),
            False,
            False,
            None,
            id="1440m-sent-at-1438m-allows",
        ),
        pytest.param(
            1440,
            timedelta(minutes=1439),
            timedelta(minutes=1438, seconds=30),
            False,
            False,
            None,
            id="1440m-sent-at-1438m30s-allows",
        ),
        pytest.param(
            60,
            None,
            None,
            False,
            False,
            None,
            id="no-history-allows",
        ),
        pytest.param(
            60,
            timedelta(days=2),
            None,
            True,
            True,
            "DELIVERY_IN_FLIGHT",
            id="in-flight-blocks-after-cooldown-expiry",
        ),
    ],
)
def test_creation_and_send_paths_share_cooldown_history(
    monkeypatch, interval, authorized_age, sent_age, in_flight, blocked, denial
):
    creation_blocked, send_permit = asyncio.run(
        _exercise_paths(monkeypatch, interval, authorized_age, sent_age, in_flight)
    )

    assert creation_blocked is blocked
    assert send_permit.permitted is (not blocked)
    assert send_permit.denial_code == denial
