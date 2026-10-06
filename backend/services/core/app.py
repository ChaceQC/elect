"""唯一Web服务：原Gateway公开API，以及独立进程的受认证领域入口。"""

import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse

from services.common.app import create_app
from services.common.database import database_ready
from services.common.dependencies import transport_status
from services.common.errors import ErrorCode
from services.common.http import ApiError

from .lifecycle import lifespan


async def domain_health(context):
    state = context.state
    try:
        async with asyncio.timeout(3):
            await database_ready(state.database, state.migration_head)
        components = await transport_status(state.runtime)
        supervisor = state.background
        roles = supervisor.snapshot() if supervisor else {}
        status = "ready" if all(components.values()) else "degraded"
        if supervisor:
            if not supervisor.available():
                status = "not_ready"
            elif any(value["status"] != "ready" for value in roles.values()):
                status = "degraded"
        return {"status": status, "components": components, "background_roles": roles}
    except Exception:
        return {"status": "not_ready"}


def core_app():
    app = create_app("gateway", business=True, background=False)
    app.router.lifespan_context = lifespan
    # 替换工厂的Gateway健康入口，公开业务路由保持原样。
    app.router.routes[:] = [route for route in app.router.routes
                           if getattr(route, "path", None) not in {"/health/ready", "/health/live"}]

    @app.get("/health/live")
    async def live():
        return {"service": "core", "status": "live"}

    @app.get("/health/ready")
    async def ready():
        results = await asyncio.gather(*(domain_health(c) for c in app.state.domains.values()))
        domains = dict(zip(app.state.domains, results, strict=True))
        statuses = {value["status"] for value in results}
        status = "not_ready" if "not_ready" in statuses else (
            "degraded" if "degraded" in statuses else "ready")
        return JSONResponse({"service": "core", "status": status, "domains": domains},
                            status_code=503 if status == "not_ready" else 200)

    @app.api_route("/domains/{domain}/internal/v1/{path:path}", methods=["GET", "POST"])
    async def internal(domain: str, path: str, request: Request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ApiError(401, ErrorCode.INVALID_ARGUMENT, "服务身份或权限无效")
        try:
            body = await request.body()
            payload = await request.json() if body else None
        except ValueError:
            raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "请求参数不正确") from None
        return await app.state.dispatcher.invoke(domain, "/" + path, request.method,
                                                authorization[7:], payload,
                                                request_id=request.state.request_id)

    return app


app = core_app()
