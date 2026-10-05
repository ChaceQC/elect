"""工作进度健康信息，不用空循环冒充尚未实现的业务 Worker。"""

import json
import os
import time
from pathlib import Path

HEARTBEAT_DIR = Path("/tmp/elect-job-health")


class Heartbeat:
    def __init__(self, service, role, *, max_age=20):
        self.path = HEARTBEAT_DIR / f"{service}-{role}.json"
        self.max_age = max_age
        self.document = {
            "service": service,
            "role": role,
            "last_success": 0,
            "last_activity": None,
            "processed": 0,
            "failures": 0,
            "status": "starting",
            "last_tick": 0,
            "max_age": max_age,
        }
        self._save()

    def write(self, *, healthy, activity=False):
        now = time.time()
        self.document.update(status="ready" if healthy else "degraded", last_tick=now)
        if healthy:
            self.document["last_success"] = now
        else:
            self.document["failures"] += 1
        if activity:
            self.document.update(last_activity=now, processed=self.document["processed"] + 1)
        self._save()

    def finish(self, status):
        self.document.update(status=status, last_tick=time.time())
        self._save()

    def snapshot(self):
        value = dict(self.document)
        if value["status"] in {"ready", "degraded"}:
            if time.time() - value["last_tick"] >= self.max_age:
                value["status"] = "stale"
        return value

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.document))
        os.replace(temporary, self.path)


def job_healthy():
    try:
        documents = [json.loads(path.read_text()) for path in HEARTBEAT_DIR.glob("*.json")]
        return bool(documents) and all(
            document["status"] == "ready"
            and time.time() - document["last_success"] < document["max_age"]
            for document in documents
        )
    except Exception:
        return False
