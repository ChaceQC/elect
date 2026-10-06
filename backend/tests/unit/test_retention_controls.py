"""维护断点隔离与冷归档失败关闭的文件级边界。"""

from datetime import datetime, timedelta

import pytest

from services.common.admission import enforce_budget
from services.common.http import ApiError
from services.deployment.retention import checkpoint


def test_checkpoint_requires_same_domain_kind_cutoff_and_mode(tmp_path):
    path = tmp_path / "checkpoint.json"
    identity = ["room", "room_operations", "2026-01-01T00:00:00+08:00", False]
    assert checkpoint(path, identity) == ""
    checkpoint(path, identity, "0011")
    assert checkpoint(path, identity) == "0011"
    with pytest.raises(ValueError, match="模式不匹配"):
        checkpoint(path, [*identity[:3], True])


@pytest.mark.parametrize("daily", [48, 60])
def test_browser_production_daily_budget_rolls_24_hours(daily):
    now = datetime(2026, 10, 6)
    recent = {"now": now, "earliest": now-timedelta(hours=12), "daily": daily, "minute": 0}
    with pytest.raises(ApiError) as error:
        enforce_budget(recent, 0, daily=daily)
    assert error.value.status == 429 and error.value.retry_after_seconds == 43201
    enforce_budget({**recent, "daily": daily-1}, 0, daily=daily)
