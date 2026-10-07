"""单一fatal入口；独立监督线程保证事件循环/原生线程卡住时仍能有界退出。"""

import asyncio
import os
import threading
import time

from .logging import configure_logging, log


class ProcessControl:
    def __init__(self, service, drain_seconds, *, final_seconds=5, hard_exit=os._exit):
        self.service, self.drain_seconds = service, drain_seconds
        self.final_seconds, self.hard_exit = final_seconds, hard_exit
        self.supervisors, self.probes, self.callbacks = [], [], []
        self.failure, self.stop_started, self.hard_at = None, None, None
        self.exhausted, self.logged = False, False
        self.lock, self.done = threading.RLock(), threading.Event()
        self.loop = self.thread = self.stop = None

    def bind(self):
        self.loop, self.stop = asyncio.get_running_loop(), asyncio.Event()
        self.thread = threading.Thread(target=self._watch, name="elect-supervisor", daemon=True)
        self.thread.start()

    def register(self, supervisor):
        with self.lock:
            self.supervisors.append(supervisor)
        if self.stop_started is not None:
            supervisor.request_stop()

    def watch(self, domain, role, probe):
        with self.lock:
            self.probes.append((domain, role, probe))

    def request_stop(self):
        with self.lock:
            if self.stop_started is None:
                self.stop_started = time.monotonic()
                self.hard_at = self.stop_started + self.drain_seconds + self.final_seconds
        self._schedule_stop()

    def fail(self, domain, role, reason, *, exhausted=False):
        with self.lock:
            if self.failure is None:
                self.failure = {"domain": domain, "role": role, "error_code": reason}
            if exhausted:
                self.exhausted = True
                limit = time.monotonic() + self.final_seconds
                self.hard_at = min(self.hard_at, limit) if self.hard_at is not None else limit
            if self.stop_started is None:
                self.stop_started = time.monotonic()
                if self.hard_at is None:
                    self.hard_at = self.stop_started + self.drain_seconds + self.final_seconds
        self._schedule_stop()

    def _schedule_stop(self):
        if self.loop and not self.loop.is_closed():
            try:
                current = asyncio.get_running_loop()
            except RuntimeError:
                current = None
            if current is self.loop:
                self._deliver_stop()
            else:
                self.loop.call_soon_threadsafe(self._deliver_stop)

    def _deliver_stop(self):
        self.stop.set()
        for supervisor in list(self.supervisors):
            supervisor.request_stop()
        for callback in self.callbacks:
            callback()
        self._log_failure()

    def _log_failure(self):
        if self.failure and not self.logged:
            self.logged = True
            log("process_fatal", service=self.service, **self.failure)

    def _watch(self):
        while not self.done.wait(0.25):
            now = time.monotonic()
            with self.lock:
                stopping, hard_at = self.stop_started, self.hard_at
                supervisors, probes = list(self.supervisors), list(self.probes)
            if hard_at is not None and now >= hard_at:
                self.hard_exit(1)
                return
            if stopping is not None:
                if now >= stopping + self.drain_seconds and self.failure is None:
                    self.fail(self.service, "process", "DRAIN_EXHAUSTED")
                continue
            try:
                self._check_health(supervisors, probes)
            except Exception:
                self.fail(self.service, "process", "SUPERVISION_FAILED")

    def _check_health(self, supervisors, probes):
        for supervisor in supervisors:
            for role, value in supervisor.snapshot().items():
                if value["status"] in {"failed", "stale", "not_ready", "stopped"}:
                    self.fail(supervisor.app.state.runtime.service, role,
                              value.get("reason", "BACKGROUND_NOT_READY"))
        for domain, role, probe in probes:
            reason = probe()
            if reason:
                self.fail(domain, role, reason)

    def finish(self):
        self._log_failure()
        # 原生计算已耗尽关闭预算：保持daemon监督到最终os._exit，不能在解释器join前撤销。
        if not self.exhausted:
            self.done.set()
            if self.thread:
                self.thread.join(timeout=1)
        return self.failure is not None


def run_managed(service, entry, *, drain_seconds=None):
    from .background import background_enabled, shutdown_timeout

    configure_logging()
    budget = (180 if service == "core" else shutdown_timeout(service)) \
        if drain_seconds is None else drain_seconds
    control = ProcessControl(service, budget) if background_enabled() else None

    async def run():
        if control:
            control.bind()
        await entry(control)

    failed = False
    try:
        asyncio.run(run())
    except Exception:
        failed = True
        if control:
            control.fail(service, "process", "PROCESS_FAILED")
        else:
            log("process_failed", service=service, error_code="PROCESS_FAILED")
    finally:
        failed = (control.finish() if control else False) or failed
    if failed:
        raise SystemExit(1)
