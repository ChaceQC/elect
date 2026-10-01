from datetime import datetime, timedelta

from services.monitoring.scheduler import latest_slot


def test_missed_slots_only_schedule_latest_and_keep_anchor():
    anchor = datetime(2026, 10, 1, 0, 7, 23)
    slot, following = latest_slot(anchor, anchor + timedelta(hours=5, minutes=20), 75)
    assert slot == anchor + timedelta(hours=5)
    assert following == anchor + timedelta(hours=6, minutes=15)


def test_exact_due_slot_and_initial_enable():
    anchor = datetime(2026, 10, 1)
    assert latest_slot(anchor, anchor, 60) == (anchor, anchor + timedelta(hours=1))
    assert latest_slot(anchor, anchor + timedelta(hours=1), 60) == (
        anchor + timedelta(hours=1),
        anchor + timedelta(hours=2),
    )
