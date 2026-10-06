"""R5隔离进程检查：真实双槽循环和三个入口，仅替换学校工作与资源初始化。"""

import argparse
import asyncio
import os
import signal
from functools import partial
from unittest.mock import AsyncMock, patch

import uvicorn

from scripts.r3_process_probe import Probe
from services.common import app as app_module
from services.common.background import Role
from services.common.business_worker import business_loop
from services.common.server import ManagedServer
from services.core.app import core_app
from services.payment import process, wakeups
from services.room import worker


class ReadProbe(Probe):
    def __init__(self, mode, service):
        super().__init__(mode, "normal", service)
        self.reads, self.active = 0, 0
        self.both = None

    async def tick(self, app, heartbeat=None, **kwargs):
        self.reads += 1
        self.active += 1
        assert self.reads <= 2  # SIGTERM后不能继续领取。
        if self.both is None:
            self.both = asyncio.Event()
        with heartbeat.work(1, lease_seconds=1):
            if self.active == 2:
                self.both.set()
                os.kill(os.getpid(), signal.SIGTERM)
            await self.both.wait()
            await asyncio.sleep(.05)  # 停止信号期间两项在途工作仍完成drain。
        self.active -= 1
        return True

    def roles(self, service):
        if service == self.service:
            return [Role("worker", partial(business_loop, "room"))] if service == "room" else [
                Role("reconciliation", partial(process.role_loop, "reconciliation"))]

        async def idle(app, stop, heartbeat, hub=None):
            heartbeat.write(healthy=True)
            await stop.wait()
        return [Role("probe", idle)]

    async def standalone(self, control):
        if self.service == "room":
            from services.common.business_worker import run

            await run("room", control=control)
        else:
            await process.run("worker", control=control)

    async def server(self, control):
        app = (core_app() if self.mode == "core"
               else app_module.create_app(self.service, business=True))
        server = ManagedServer(uvicorn.Config(app, host="127.0.0.1", port=0, access_log=False,
            log_level="critical", timeout_graceful_shutdown=.4), app, control)
        await server.serve()

    def run(self):
        with (patch.object(worker, "room_tick", self.tick),
              patch.object(worker, "control_tick", AsyncMock(return_value=False)),
              patch.object(process, "check_tick", self.tick),
              patch.object(process, "worker_tick", AsyncMock(return_value=False)),
              patch.object(wakeups, "drain", AsyncMock())):
            super().run()
        assert self.reads == 2 and self.active == 0
        print("R5_READ_DRAIN_OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["core", "combined", "standalone"], required=True)
    parser.add_argument("--service", choices=["room", "payment"], required=True)
    args = parser.parse_args()
    ReadProbe(args.mode, args.service).run()
