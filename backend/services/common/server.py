"""关闭访问日志，避免框架默认日志泄露查询串或认证参数。"""

import os
from contextlib import contextmanager
from importlib import import_module

import uvicorn

from .background import shutdown_timeout
from .process_control import run_managed


class ManagedServer(uvicorn.Server):
    def __init__(self, config, app, control=None):
        super().__init__(config)
        self.app = app
        self.control = control
        app.state.process_control = control
        if control:
            control.callbacks.append(self.request_exit)

    def request_exit(self):
        self.should_exit = True

    async def startup(self, sockets=None):
        await super().startup(sockets)
        # Uvicorn在startup后should_exit时直接return；补上已成功启动的lifespan关闭。
        if self.should_exit and self.started:
            await self.shutdown(sockets)
        elif not self.started and self.control:
            self.control.fail(self.control.service, "api", "API_START_FAILED")

    async def shutdown(self, sockets=None):
        if self.control:
            self.control.request_stop()
        await super().shutdown(sockets)

    @contextmanager
    def capture_signals(self):
        with super().capture_signals():
            try:
                yield
            finally:
                # 已协调完成的SIGTERM正常返回0，不在资源关闭后重新抛出同一信号。
                self._captured_signals.clear()

    def handle_exit(self, sig, frame):
        if self.control:
            self.control.request_stop()
        supervisor = getattr(self.app.state, "background", None)
        if supervisor:
            supervisor.request_stop()
        super().handle_exit(sig, frame)


def serve(service):
    if os.environ.get("ELECT_CORE_ONLY") == "true" and service != "core":
        raise SystemExit("核心组合禁止重复启动独立领域进程")
    app = import_module(f"services.{service}.app").app
    grace = (180 if service == "core" else shutdown_timeout(service)
             if os.environ.get("ELECT_PROCESS_MODE") == "combined" else 30)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        proxy_headers=False,
        log_level="warning",
        ssl_certfile=os.environ.get("ELECT_INTERNAL_TLS_CERT_FILE"),
        ssl_keyfile=os.environ.get("ELECT_INTERNAL_TLS_KEY_FILE"),
        timeout_graceful_shutdown=grace,
    )
    async def entry(control):
        await ManagedServer(config, app, control).serve()

    run_managed(service, entry, drain_seconds=grace)
