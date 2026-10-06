"""可控单调时钟覆盖业务失败、租约、MQ降级与独立槽；不等待真实60秒。"""

from types import SimpleNamespace

import pytest

from services.common import health_state, heartbeat
from services.common.heartbeat import Heartbeat, job_healthy


@pytest.fixture
def clock(monkeypatch, tmp_path):
    value = SimpleNamespace(wall=1000.0, mono=100.0)
    timer = SimpleNamespace(time=lambda: value.wall, monotonic=lambda: value.mono)
    monkeypatch.setattr(heartbeat, "time", timer)
    monkeypatch.setattr(health_state, "time", timer)
    monkeypatch.setattr(heartbeat, "HEARTBEAT_DIR", tmp_path / "health")
    return value


def test_successful_idle_scan_and_mq_degradation_agree_with_file_probe(clock):
    beat = Heartbeat("room", "relay", max_age=45)
    for _ in range(4):
        beat.write(healthy=True, degraded="rabbitmq")
        assert beat.snapshot()["status"] == "degraded" and job_healthy()
        clock.mono += 30
    beat.write(healthy=True)
    assert beat.snapshot()["degraded_reason"] is None and job_healthy()


def test_connection_probe_cannot_clear_continuous_business_failure(clock):
    beat = Heartbeat("room", "worker")
    beat.write(healthy=True)
    beat.write(healthy=False)
    for age in (10, 30, 59):
        clock.mono = 100 + age
        beat.tick()  # checked_tick中SELECT 1只能触达这里。
        assert beat.snapshot()["status"] == "degraded" and job_healthy()
    clock.mono = 160
    beat.tick()
    assert beat.snapshot()["reason"] == "BUSINESS_FAILURE_BUDGET" and not job_healthy()
    assert beat.snapshot()["last_success"] == 1000
    beat.write(healthy=True)
    assert beat.snapshot()["consecutive_failures"] == 0 and job_healthy()


def test_only_connection_ticks_never_count_as_business_progress(clock):
    beat = Heartbeat("school_adapter", "cleanup")
    beat.write(healthy=True)
    clock.mono += 60
    beat.tick()
    assert beat.snapshot()["reason"] == "BUSINESS_PROGRESS_STALE"
    assert not job_healthy()


def test_scheduled_idle_and_first_transient_failure_have_distinct_budgets(clock):
    beat = Heartbeat("school_adapter", "cleanup")
    beat.write(healthy=True, next_scan_in=60)
    clock.mono += 60
    beat.tick()
    assert job_healthy()  # 60秒清理到期不与监督线程抢同一个时间边界。
    beat.write(healthy=False)
    clock.mono += 59
    beat.tick()
    assert beat.snapshot()["status"] == "degraded" and job_healthy()
    clock.mono += 1
    beat.tick()
    assert beat.snapshot()["reason"] == "BUSINESS_FAILURE_BUDGET"


@pytest.mark.parametrize("expire", ["deadline", "lease"])
def test_long_inflight_uses_real_renewal_without_refreshing_success(clock, expire):
    beat = Heartbeat("monitoring", "worker")
    beat.write(healthy=True)
    with beat.work(90, lease_seconds=45) as work:
        for age in (30, 60, 75):
            clock.mono = 100 + age
            work.renew(45)
            assert beat.snapshot()["status"] == "ready" and job_healthy()
            assert beat.snapshot()["success_monotonic"] == 100
        if expire == "lease":
            work.renew(1)
            clock.mono += 1
        else:
            clock.mono = 190
        beat.tick()
        assert beat.snapshot()["reason"] == "WORK_DEADLINE_OR_LEASE"
        assert not job_healthy()


def test_two_slots_cannot_mask_failure_and_wall_clock_rollback_is_harmless(clock):
    beat = Heartbeat("monitoring", "worker")
    bad, good = beat.child("0"), beat.child("1")
    assert beat.snapshot()["status"] == "starting"
    bad.write(healthy=False)
    good.write(healthy=True)
    clock.wall -= 3600
    clock.mono += 59
    bad.tick()
    good.write(healthy=True)
    assert beat.snapshot()["status"] == "degraded" and job_healthy()
    clock.mono += 1
    bad.tick()
    good.write(healthy=True)
    assert beat.snapshot()["status"] == "not_ready" and not job_healthy()
    bad.write(healthy=True)
    assert job_healthy()
    clock.mono += 21
    good.write(healthy=True)
    assert beat.snapshot()["slots"]["0"]["status"] == "stale" and not job_healthy()
