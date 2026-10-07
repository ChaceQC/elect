"""同域异步角色监督；信号由服务入口负责，退出前停止领取新任务。"""

import asyncio
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from .broker import BrokerHub
from .health_state import AVAILABLE
from .heartbeat import Heartbeat
from .logging import log_failure


@dataclass(frozen=True)
class Role:
    name: str
    run: Callable
    max_age: float = 20


def background_enabled():
    value = os.environ.get("ELECT_BACKGROUND_ENABLED", "true")
    if value not in {"true", "false"}:
        raise RuntimeError("后台开关只允许true/false")
    return value == "true"


def process_mode():
    value = os.environ.get("ELECT_PROCESS_MODE", "standalone")
    if value not in {"standalone", "combined"}:
        raise RuntimeError("进程模式只允许standalone/combined")
    return value


def require_standalone():
    if (not background_enabled() or process_mode() != "standalone"
            or os.environ.get("ELECT_CORE_ONLY") == "true"):
        raise RuntimeError("当前部署禁止独立后台入口")


def shutdown_timeout(service):
    # 从统一停止信号开始计时，覆盖各领域原有的最长在途预算。
    return {"identity": 125, "room": 125, "monitoring": 100, "payment": 180}.get(service, 30)


class BackgroundSupervisor:
    def __init__(self, app, roles, *, shutdown_timeout=100):
        self.app, self.roles = app, roles
        if len({role.name for role in roles}) != len(roles):
            raise ValueError("后台角色重复")
        self.stop = asyncio.Event()
        self.closed = False
        self.stop_started = None
        self.shutdown_timeout = shutdown_timeout
        self.broker = BrokerHub(app.state.runtime)
        self.tasks, self.heartbeats = {}, {}
        self.control = getattr(app.state, "process_control", None)
        if self.control:
            self.control.register(self)

    async def start(self):
        if self.tasks or self.stop.is_set():
            raise RuntimeError("后台生命周期不能重复启动")
        for role in self.roles:
            heartbeat = Heartbeat(self.app.state.runtime.service, role.name, max_age=role.max_age)
            self.heartbeats[role.name] = heartbeat
            self.tasks[role.name] = asyncio.create_task(
                self._run(role, heartbeat), name=f"background:{role.name}"
            )
            self.tasks[role.name].add_done_callback(
                lambda task, name=role.name: self._finished(name, task),
            )
        await asyncio.sleep(0)

    def _finished(self, name, task):
        if not self.stop.is_set():
            self.heartbeats[name].finish("failed")
            self.fail(name, "BACKGROUND_CANCELLED" if task.cancelled() else "BACKGROUND_RETURNED")

    async def _run(self, role, heartbeat):
        try:
            await role.run(self.app, self.stop, heartbeat, self.broker)
        except asyncio.CancelledError:
            heartbeat.finish("stopped" if self.stop.is_set() else "failed")
            if not self.stop.is_set():
                self.fail(role.name, "BACKGROUND_CANCELLED")
            raise
        except Exception as error:
            heartbeat.finish("failed")
            log_failure("background_role_failed", error,
                        service=self.app.state.runtime.service, role=role.name)
            self.fail(role.name, "BACKGROUND_ROLE_FAILED")
        else:
            heartbeat.finish("stopped" if self.stop.is_set() else "failed")
            if not self.stop.is_set():
                self.fail(role.name, "BACKGROUND_RETURNED")

    def fail(self, role, reason):
        if self.control:
            self.control.fail(self.app.state.runtime.service, role, reason)
        self.request_stop()

    def snapshot(self):
        return {name: heartbeat.snapshot() for name, heartbeat in tuple(self.heartbeats.items())}

    def available(self):
        return (
            bool(self.tasks)
            and not self.stop.is_set()
            and all(
                not self.tasks[name].done() and value["status"] in AVAILABLE
                for name, value in self.snapshot().items()
            )
        )

    def request_stop(self):
        if not self.stop.is_set():
            self.stop_started = time.monotonic()
            self.stop.set()

    async def close(self):
        if self.closed:
            return
        self.request_stop()
        remaining = max(0, self.shutdown_timeout - (time.monotonic() - self.stop_started))
        try:
            if self.tasks:
                _, pending = await asyncio.wait(self.tasks.values(), timeout=remaining)
                if pending and self.control:
                    self.control.fail(self.app.state.runtime.service, "process", "DRAIN_EXHAUSTED")
                for task in pending:
                    task.cancel()
                await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        finally:
            await self.broker.close()
            self.closed = True


async def start_background(app, service):
    previous = getattr(app.state, "background", None)
    if previous and not previous.closed:
        raise RuntimeError("已有后台生命周期须先完成退出")
    # 显式关闭优先于合并模式；恢复环境即使有合并配置也不能启动角色。
    enabled, mode = background_enabled(), process_mode()
    app.state.background = None
    if not enabled or mode == "standalone":
        return
    from .background_roles import roles

    configured = roles(service)
    if not configured:
        return
    supervisor = BackgroundSupervisor(app, configured, shutdown_timeout=shutdown_timeout(service))
    app.state.background = supervisor
    if supervisor.stop.is_set():
        return
    await supervisor.start()


async def run_standalone(app, configured, control=None):
    """独立入口复用相同角色监督、停止时刻和退出预算。"""
    import signal

    service = app.state.runtime.service
    app.state.process_control = control
    supervisor = BackgroundSupervisor(app, configured, shutdown_timeout=(
        control.drain_seconds if control else shutdown_timeout(service)
    ))
    app.state.background = supervisor
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, control.request_stop
                                if control else supervisor.request_stop)
    try:
        if not supervisor.stop.is_set():
            await supervisor.start()
        await supervisor.stop.wait()
    finally:
        await supervisor.close()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)
