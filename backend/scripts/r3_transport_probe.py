"""一次性实际MySQL/RabbitMQ健康探针；无业务身份或外部副作用。"""

import argparse
import json
import urllib.request
from contextlib import asynccontextmanager
from types import SimpleNamespace

import uvicorn
from pydantic import SecretStr

from scripts.r3_recovery_state import RecoveryState
from services.common.app import create_app
from services.common.background import BackgroundSupervisor, Role
from services.common.database import migration_head
from services.common.job import transport_loop
from services.common.process_control import run_managed
from services.common.server import ManagedServer


async def entry(control):
    state = RecoveryState("elect_r3_mq")
    app = create_app("room", business=False, background=False)

    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime = SimpleNamespace(
            service="room", redis_url=None,
            amqp_url=SecretStr("amqp://r3synthetic:r3synthetic@query-mq/"),
        )
        app.state.database = state.engines["room"]
        app.state.migration_head = migration_head("room")
        supervisor = BackgroundSupervisor(app, [Role("relay", transport_loop, max_age=45)],
                                          shutdown_timeout=30)
        app.state.background = supervisor
        try:
            await supervisor.start()
            yield
        finally:
            await supervisor.close()
            await state.close()

    app.router.lifespan_context = lifespan
    await ManagedServer(uvicorn.Config(app, host="0.0.0.0", port=8000, access_log=False,
                                       log_level="critical", timeout_graceful_shutdown=30),
                        app, control).serve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", choices=["ready", "degraded"])
    args = parser.parse_args()
    if args.expect:
        with urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=5) as response:
            assert response.status == 200
            value = json.load(response)
        assert value["status"] == args.expect
        role = value["background_roles"]["relay"]
        assert role["status"] == args.expect and role["consecutive_failures"] == 0
        print(json.dumps({"status": value["status"], "role": role["status"],
                          "failure_count": role["consecutive_failures"]}))
    else:
        run_managed("room", entry, drain_seconds=30)


if __name__ == "__main__":
    main()
