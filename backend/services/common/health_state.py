"""API、独立探针和监督线程共用单调时钟判定，不信任状态字符串。"""

import time
from copy import deepcopy

FAILURE_SECONDS = 60
AVAILABLE = {"ready", "degraded"}


def assess(document, *, now=None):
    now = time.monotonic() if now is None else now
    value = deepcopy(document)
    if value["status"] in {"failed", "stopped"}:
        return value
    if value.get("slots"):
        slots = {key: assess(slot, now=now) for key, slot in value["slots"].items()}
        value["slots"] = slots
        states = {slot["status"] for slot in slots.values()}
        value["status"] = ("not_ready" if states & {"failed", "stale", "not_ready", "stopped"}
                           else "starting" if "starting" in states else
                           "degraded" if "degraded" in states else "ready")
        value["last_success"] = min(slot["last_success"] for slot in slots.values())
        value["last_tick"] = max(slot["last_tick"] for slot in slots.values())
        value["failures"] = sum(slot["failures"] for slot in slots.values())
        return value
    age = now - value["tick_monotonic"]
    if age < 0 or age >= value["max_age"]:
        value.update(status="stale", reason="HEARTBEAT_STALE")
    elif any(now >= work["deadline"] or (
        work["lease_until"] is not None and now >= work["lease_until"]
    ) for work in value["inflight"].values()):
        value.update(status="not_ready", reason="WORK_DEADLINE_OR_LEASE")
    elif value["failure_since_monotonic"] is not None and (
        now - value["failure_since_monotonic"] >= value["failure_budget"]
    ):
        value.update(status="not_ready", reason="BUSINESS_FAILURE_BUDGET")
    elif not value["inflight"] and value["failure_since_monotonic"] is None and (
        now >= progress_deadline(value)
    ):
        value.update(status="not_ready", reason="BUSINESS_PROGRESS_STALE")
    elif value["inflight"] and value["status"] == "starting":
        value["status"] = "ready"
    return value


def progress_deadline(value):
    success = value["success_monotonic"]
    deadline = (success if success is not None else value["started_monotonic"]) \
        + value["failure_budget"]
    if value.get("next_scan_monotonic") is not None:
        deadline = max(deadline, value["next_scan_monotonic"] + value["max_age"])
    if value.get("work_finished_monotonic") is not None:
        # 完成在途与写入扫描结果之间留一个事件循环交接窗口，不刷新业务成功时间。
        deadline = max(deadline, value["work_finished_monotonic"] + 1)
    return deadline


def available(document):
    return assess(document)["status"] in AVAILABLE
