"""期限边界及在途/付款/取消的页面暂停语义。"""

from datetime import UTC, datetime, timedelta

import pytest

from services.payment.check_window import deadline, expired, paused

NOW = datetime(2026, 10, 8, 6, tzinfo=UTC)


def order(**updates):
    return {"state": "status_unknown", "created_at": NOW - timedelta(minutes=15),
            "check_deadline_at": None, "observed_at": NOW, "cancel_requested_at": None,
            "check_lease_until": None, **updates}


@pytest.mark.parametrize("delta,expected", [(-1, False), (0, True), (1, True)])
def test_legacy_order_pauses_at_fifteen_minutes_without_resetting_age(delta, expected):
    row = order(observed_at=NOW + timedelta(microseconds=delta))
    assert deadline(row) == NOW
    assert paused(row) is expected


@pytest.mark.parametrize("active", [
    {"operation_in_flight": True}, {"check_lease_until": NOW + timedelta(seconds=90)},
])
def test_page_keeps_reading_until_the_current_task_finishes(active):
    row = order(**active)
    assert expired(row) and not paused(row)


def test_persisted_resume_deadline_overrides_age_but_not_a_terminal_result():
    row = order(check_deadline_at=NOW + timedelta(minutes=15))
    assert not expired(row) and not paused(row)
    assert not paused(order(state="paid_confirmed"))
    assert not paused(order(cancel_requested_at=NOW))
