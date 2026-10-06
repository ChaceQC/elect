"""仅供隔离R3进程检查：合成上下文、真实服务入口/信号/线程，绝不加载业务Secret。"""

import argparse
import asyncio
import os
import signal
import threading
import time
from contextlib import asynccontextmanager
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import uvicorn
from pydantic import SecretStr

from services.common import app as app_module
from services.common import background, background_roles, business, process_control
from services.common.server import ManagedServer
from services.core import lifecycle
from services.core.app import core_app
from services.school_adapter.infrastructure.ocr_executor import OcrExecutor

SENTINEL = "R3_SECRET_SENTINEL_SQL_JWT_COOKIE"


class Probe:
    def __init__(self, mode, fault, service="school_adapter"):
        self.mode, self.fault = mode, fault
        self.closed, self.started = [], []
        self.executor = None
        self.service = service

    @asynccontextmanager
    async def context(self, app, service, **kwargs):
        app.state.runtime = SimpleNamespace(service=service, redis_url=None, amqp_url=None)
        app.state.database, app.state.migration_head, app.state.background = None, None, None
        try:
            yield app
        finally:
            if app.state.background:
                await app.state.background.close()
            await business.close(app)
            self.closed.append(service)

    def roles(self, service):
        selected = service == ("room" if self.mode == "core" else "school_adapter")
        return [background.Role("probe", partial(self.role, selected),
                                max_age=0.1 if self.fault == "blocked_loop" else 20)]

    async def role(self, selected, app, stop, beat, hub=None):
        self.started.append(app.state.runtime.service)
        beat.write(healthy=True)
        if not selected:
            await stop.wait()
            return
        if self.fault == "return":
            return
        if self.fault == "raise":
            raise RuntimeError(SENTINEL)
        if self.fault == "cancel":
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
        if self.fault == "blocked_loop":
            time.sleep(20)  # 子进程的事件循环确实停止推进，独立监督线程仍须退出。
        if self.fault in {"business", "only_tick"}:
            beat.document["failure_budget"] = 0.1
            while not stop.is_set():
                beat.write(healthy=False) if self.fault == "business" else beat.tick()
                await asyncio.sleep(0.02)
            return
        if self.fault == "ocr":
            await self.ocr(app)
        if self.fault == "normal":
            await asyncio.sleep(0.1)
            os.kill(os.getpid(), signal.SIGTERM)
        await stop.wait()

    async def ocr(self, app):
        entered, never = threading.Event(), threading.Event()

        def solver(image):
            entered.set()
            never.wait()

        executor = self.executor = OcrExecutor(solver)
        original_close = executor.close

        async def close():
            return await original_close(timeout=0.05)  # 缩短合成drain，真实线程不能停止。

        executor.close = close
        app.state.school_sessions = SimpleNamespace(ocr_executor=executor)
        control = app.state.process_control
        control.watch("school_adapter", "ocr", executor.health_failure)
        control.callbacks.append(executor.request_stop)
        try:
            await executor.solve(b"synthetic", SimpleNamespace(remaining=lambda: 0.05))
        except TimeoutError:
            pass
        assert entered.is_set()
        executor.active_deadline = time.monotonic() - 6

    async def standalone(self, control):
        # 真实独立业务入口；只替换其业务工作函数及资源初始化。
        from services.common import business_worker, job
        from services.monitoring import job as monitoring
        from services.notification import job as notification
        from services.payment import process as payment

        async def role(service, app, stop, heartbeat, hub=None):
            await self.role(True, app, stop, heartbeat, hub)

        if self.service in {"identity", "room", "school_adapter"}:
            with patch.object(business_worker, "business_loop", role):
                await business_worker.run(self.service, control=control)
        elif self.service in {"monitoring", "notification", "payment"}:
            module = {"monitoring": monitoring, "notification": notification,
                      "payment": payment}[self.service]
            with patch.object(module, "role_loop", role), \
                    patch.object(notification, "domain_context", self.context):
                await module.run("worker", control=control)
        else:
            runtime = SimpleNamespace(service="audit", db_url=SecretStr("synthetic"),
                                      amqp_url=SecretStr("synthetic"))
            engine = SimpleNamespace(dispose=AsyncMock())
            with (
                patch.object(job, "load_runtime", lambda _: runtime),
                patch.object(job, "validate_keys", lambda _: None),
                patch.object(job, "side_effect_policy", lambda: None),
                patch.object(job, "migration_head", lambda _: "synthetic"),
                patch.object(job, "create_database", lambda _: engine),
                patch.object(job, "transport_loop", partial(self.role, True)),
            ):
                await job.run_job("audit", "audit" if self.service == "audit" else "relay",
                                  control=control)
            engine.dispose.assert_awaited_once()

    async def server(self, control):
        app = core_app() if self.mode == "core" else app_module.create_app(
            "school_adapter", business=True,
        )
        server = ManagedServer(uvicorn.Config(
            app, host="127.0.0.1", port=0, access_log=False, log_level="critical",
            timeout_graceful_shutdown=0.4,
        ), app, control)

        async def stop_disabled():
            while not server.started:
                await asyncio.sleep(0.01)
            assert app.state.process_control is None
            assert not self.started
            assert not any(t.name == "elect-supervisor" for t in threading.enumerate())
            os.kill(os.getpid(), signal.SIGTERM)

        stopper = asyncio.create_task(stop_disabled()) if self.fault == "disabled" else None
        try:
            await server.serve()
        finally:
            if stopper:
                await stopper

    def run(self):
        os.environ["ELECT_PROCESS_MODE"] = "standalone" if self.mode == "standalone" else "combined"
        os.environ["ELECT_BACKGROUND_ENABLED"] = "false" if self.fault == "disabled" else "true"
        real_control = process_control.ProcessControl
        with (
            patch.object(app_module, "domain_context", self.context),
            patch.object(lifecycle, "domain_context", self.context),
            patch.object(lifecycle, "load_runtime", lambda name, **kwargs: SimpleNamespace(
                service=name, redis_url=None, amqp_url=None,
            )),
            patch.object(background_roles, "roles", self.roles),
            patch.object(background, "shutdown_timeout", lambda service: 0.4),
            patch.object(process_control, "ProcessControl", lambda service, budget: real_control(
                service, 0.4, final_seconds=0.2,
            )),
        ):
            try:
                process_control.run_managed(
                    "core" if self.mode == "core" else self.service,
                    self.standalone if self.mode == "standalone" else self.server,
                )
            finally:
                if self.fault not in {"blocked_loop", "ocr", "restart"}:
                    expected = 0 if self.service in {"relay", "audit"} else (
                        7 if self.mode == "core" else 1)
                    assert len(self.closed) == expected, "进程必须先完成上下文关闭"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["core", "combined", "standalone"], required=True)
    parser.add_argument("--service", default="school_adapter")
    parser.add_argument("--fault", required=True, choices=[
        "return", "raise", "cancel", "business", "only_tick", "blocked_loop", "ocr",
        "normal", "disabled",
    ])
    args = parser.parse_args()
    Probe(args.mode, args.fault, args.service).run()


if __name__ == "__main__":
    main()
