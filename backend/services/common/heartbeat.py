"""工作进度健康信息，不用空循环冒充尚未实现的业务 Worker。"""

import json
import os
import time
from pathlib import Path

HEARTBEAT = Path("/tmp/elect-job-health.json")


class Heartbeat:
    def __init__(self, service, role):
        self.document = {
            "service": service,
            "role": role,
            "last_success": 0,
            "last_activity": None,
            "processed": 0,
            "failures": 0,
        }

    def write(self, *, healthy, activity=False):
        now = time.time()
        self.document.update(status="ready" if healthy else "degraded", last_tick=now)
        if healthy:
            self.document["last_success"] = now
        else:
            self.document["failures"] += 1
        if activity:
            self.document.update(last_activity=now, processed=self.document["processed"] + 1)
        temporary = HEARTBEAT.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.document))
        os.replace(temporary, HEARTBEAT)


def job_healthy():
    try:
        document = json.loads(HEARTBEAT.read_text())
        return document["status"] == "ready" and time.time() - document["last_success"] < 20
    except Exception:
        return False
