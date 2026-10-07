"""固定大小的领取游标和脱敏等待/耗时；不缓存任务或持有租约。"""

from contextlib import contextmanager
from time import monotonic

from .logging import log


class ReadSchedule:
    def __init__(self, kinds):
        self.kinds, self.turn = kinds, 0
        self.after = dict.fromkeys(kinds, b"")

    def order(self):
        start = self.turn
        self.turn = (start + 1) % len(self.kinds)
        return self.kinds[start:] + self.kinds[:start]

    def visited(self, kind, owner):
        self.after[kind] = owner


def claimed(service, kind, row, due):
    if due:
        log("read_claim_wait", service=service, role=kind,
            duration_ms=max(0, int((row["claimed_at"] - due).total_seconds() * 1000)))


@contextmanager
def processing(service, kind):
    started = monotonic()
    try:
        yield
    finally:
        log("read_processed", service=service, role=kind,
            duration_ms=int((monotonic() - started) * 1000))
