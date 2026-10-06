"""统一停止领取，等待所有领域在途工作后再释放上下文。"""

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from types import SimpleNamespace

from starlette.datastructures import State

from services.common.background import start_background
from services.common.context import domain_context
from services.common.domains import CORE_DOMAINS
from services.common.logging import configure_logging
from services.common.runtime import load_runtime
from services.common.service_client import ServiceClient

from .dispatch import Dispatcher


class CoreBackground:
    def __init__(self, contexts):
        self.contexts = contexts

    def supervisors(self):
        return [app.state.background for app in self.contexts.values()
                if getattr(app.state, "background", None)]

    def request_stop(self):
        for supervisor in self.supervisors():
            supervisor.request_stop()

    async def close(self):
        self.request_stop()
        results = await asyncio.gather(*(supervisor.close() for supervisor in self.supervisors()),
                                       return_exceptions=True)
        if any(isinstance(result, BaseException) for result in results):
            raise RuntimeError("核心后台退出失败") from None


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    if os.environ.get("ELECT_PROCESS_MODE") != "combined":
        raise RuntimeError("核心入口必须使用合并后台模式")
    contexts = {name: SimpleNamespace(state=State()) for name in CORE_DOMAINS}
    dispatcher = Dispatcher(contexts)
    app.state.domains, app.state.dispatcher = contexts, dispatcher
    supervisor = CoreBackground(contexts)
    app.state.background = supervisor
    async with AsyncExitStack() as stack:
        try:
            for name, context in {"gateway": app, **contexts}.items():
                context.state.process_control = getattr(app.state, "process_control", None)
                runtime = load_runtime(name, path=f"/run/secrets/{name}_runtime")
                context.state.service_client_factory = lambda value: ServiceClient(
                    value, local=dispatcher)
                context.state.mail_sender = False
                if name in {"monitoring", "notification"}:
                    context.state.secret_files = {
                        "ELECT_EMAIL_KEY_FILE": f"/run/secrets/{name}_encryption_key_bundle"
                    }
                await stack.enter_async_context(domain_context(context, name, runtime=runtime))
            app.state.background = supervisor
            # 全部领域已初始化才启动后台，避免循环调用碰到半初始化上下文。
            for name, context in contexts.items():
                await start_background(context, name)
            yield
        finally:
            await supervisor.close()
            # gateway的通用上下文不要再次关闭聚合监督器。
            app.state.background = None
