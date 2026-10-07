"""循环存活、业务成功、在途续租分别记录；多执行槽不能互相刷新成功。"""

import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from .health_state import FAILURE_SECONDS, assess, available

HEARTBEAT_DIR = Path("/tmp/elect-job-health")


class Work:
    def __init__(self, heartbeat, key):
        self.heartbeat, self.key = heartbeat, key

    def renew(self, seconds):
        now = time.monotonic()
        self.heartbeat.document["inflight"][self.key].update(
            last_renew=time.time(), lease_until=now + seconds,
        )
        self.heartbeat.tick()

    def committing(self):
        # 已持有防接管行锁时由事务和原deadline保护，不能凭普通SELECT 1调用。
        self.heartbeat.document["inflight"][self.key]["lease_until"] = None
        self.heartbeat.tick()


class Heartbeat:
    def __init__(self, service, role, *, max_age=20, parent=None):
        self.path = HEARTBEAT_DIR / f"{service}-{role}.json"
        self.max_age, self.parent = max_age, parent
        self.children, self.work_sequence = {}, 0
        now = time.monotonic()
        self.document = {
            "service": service, "role": role, "status": "starting", "max_age": max_age,
            "last_success": 0, "last_activity": None, "processed": 0, "failures": 0,
            "last_tick": time.time(), "tick_monotonic": now, "started_monotonic": now,
            "success_monotonic": None, "consecutive_failures": 0,
            "failure_since": None, "failure_since_monotonic": None,
            "failure_budget": FAILURE_SECONDS, "degraded_reason": None, "inflight": {},
            "next_scan_monotonic": None, "work_finished_monotonic": None,
        }
        self.published = deepcopy(self.document)
        if parent is None:
            self._save()

    def child(self, slot):
        child = Heartbeat(self.document["service"], self.document["role"],
                          max_age=self.max_age, parent=self)
        self.children[slot] = child
        self._save()
        return child

    def tick(self):
        self.document.update(last_tick=time.time(), tick_monotonic=time.monotonic())
        self._save()

    def write(self, *, healthy, activity=False, degraded=None, next_scan_in=None):
        now, clock = time.time(), time.monotonic()
        self.document.update(status="ready" if healthy and not degraded else "degraded",
                             last_tick=now, tick_monotonic=clock, degraded_reason=degraded,
                             next_scan_monotonic=clock + next_scan_in
                             if healthy and next_scan_in is not None else None)
        if healthy:
            self.document.update(last_success=now, success_monotonic=clock,
                                 consecutive_failures=0, failure_since=None,
                                 failure_since_monotonic=None)
        else:
            self.document["failures"] += 1
            self.document["consecutive_failures"] += 1
            if self.document["failure_since_monotonic"] is None:
                self.document.update(failure_since=now, failure_since_monotonic=clock)
        if activity:
            self.document.update(last_activity=now, processed=self.document["processed"] + 1)
        self._save()

    @contextmanager
    def work(self, seconds, *, lease_seconds=None):
        self.work_sequence += 1
        key, now = str(self.work_sequence), time.monotonic()
        self.document["inflight"][key] = {
            "started_at": time.time(), "deadline": now + seconds, "last_renew": None,
            "lease_until": now + lease_seconds if lease_seconds is not None else None,
        }
        self.tick()
        try:
            yield Work(self, key)
        finally:
            del self.document["inflight"][key]
            self.document["work_finished_monotonic"] = time.monotonic()
            self.tick()

    def finish(self, status):
        self.document["status"] = status
        self.tick()

    def raw(self):
        value = dict(self.document)
        if self.children:
            value["slots"] = {key: child.raw() for key, child in self.children.items()}
        return value

    def snapshot(self):
        return assess(self.published)

    def _save(self):
        # 只在事件循环线程发布不可变快照；监督线程不遍历正在变更的在途字典。
        self.published = deepcopy(self.raw())
        if self.parent:
            self.parent._save()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.published), encoding="utf-8")
        os.replace(temporary, self.path)


def job_healthy():
    try:
        documents = [json.loads(path.read_text(encoding="utf-8"))
                     for path in HEARTBEAT_DIR.glob("*.json")]
        return bool(documents) and all(available(document) for document in documents)
    except Exception:
        return False
