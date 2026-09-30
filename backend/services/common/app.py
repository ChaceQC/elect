"""T1 服务工厂：运行基础与关闭的业务入口，不签发模拟会话。"""

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .database import create_database, database_ready
from .http import ApiError, install_http
from .logging import configure_logging
from .runtime import load_runtime, public_origin, side_effect_policy
from .security import Principal, require_principal, validate_keys


def create_app(service: str):
    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        runtime = load_runtime(service)
        validate_keys(runtime)
        app.state.runtime = runtime
        app.state.public_origin = public_origin()
        app.state.side_effect_policy = side_effect_policy()
        engine = create_database(runtime.db_url.get_secret_value()) if runtime.db_url else None
        app.state.database = engine
        try:
            yield
        finally:
            if engine:
                await engine.dispose()

    app = FastAPI(title=f"elect-{service}", lifespan=lifespan, docs_url=None, redoc_url=None)
    install_http(app, service)

    @app.get("/internal/v1/context")
    async def context(
        principal: Annotated[Principal, Depends(require_principal("foundation:read"))],
    ):
        return {
            "service": principal.service,
            "user_id": str(principal.user_id) if principal.user_id else None,
            "session_version": principal.session_version,
            "request_id": str(principal.request_id),
        }

    @app.get("/health/live")
    async def live():
        return {"service": service, "status": "live"}

    @app.get("/health/ready")
    async def ready():
        try:
            if app.state.database:
                async with asyncio.timeout(3):
                    await database_ready(app.state.database, f"{service}_0001")
            return {"service": service, "status": "ready", "business_enabled": False}
        except Exception:
            return JSONResponse(
                status_code=503, content={"service": service, "status": "not_ready"}
            )

    if service == "gateway":
        from services.gateway.contract_routes import ENDPOINTS

        from .errors import ErrorCode

        async def unavailable(request: Request):
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                from .browser_security import require_origin

                require_origin(request)
            raise ApiError(403, ErrorCode.FEATURE_DISABLED, "该功能尚未开放")

        for endpoint in ENDPOINTS:
            app.add_api_route(
                f"/api/v1{endpoint.path}",
                unavailable,
                methods=[endpoint.method.upper()],
                name=endpoint.name,
            )
    return app
