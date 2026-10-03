"""关闭访问日志，避免框架默认日志泄露查询串或认证参数。"""

import os
from importlib import import_module

import uvicorn


class ManagedServer(uvicorn.Server):
    def __init__(self, config, app):
        super().__init__(config)
        self.app = app

    def handle_exit(self, sig, frame):
        supervisor = getattr(self.app.state, "background", None)
        if supervisor:
            supervisor.request_stop()
        super().handle_exit(sig, frame)


def serve(service):
    app = import_module(f"services.{service}.app").app
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        proxy_headers=False,
        log_level="warning",
        ssl_certfile=os.environ.get("ELECT_INTERNAL_TLS_CERT_FILE"),
        ssl_keyfile=os.environ.get("ELECT_INTERNAL_TLS_KEY_FILE"),
        timeout_graceful_shutdown=(
            100 if os.environ.get("ELECT_PROCESS_MODE") == "combined" else None
        ),
    )
    ManagedServer(config, app).run()
