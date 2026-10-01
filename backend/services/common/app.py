"""T1 服务工厂：运行基础与关闭的业务入口，不签发模拟会话。"""

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .database import create_database, database_ready, migration_head
from .dependencies import transport_status
from .http import ApiError, install_http
from .logging import configure_logging
from .runtime import load_runtime, public_origin, side_effect_policy
from .security import Principal, require_principal, validate_keys


def create_app(service: str, *, business=False):
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
        app.state.migration_head = migration_head(service) if engine else None
        try:
            if business:
                from .business import initialize

                await initialize(app, service)
            yield
        finally:
            if business:
                from .business import close

                await close(app)
            if engine:
                await engine.dispose()

    app = FastAPI(
        title=f"elect-{service}", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
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
                    await database_ready(app.state.database, app.state.migration_head)
            components = await transport_status(app.state.runtime)
            return {
                "service": service,
                "status": "ready" if all(components.values()) else "degraded",
                "components": components,
                "business_enabled": business,
            }
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
            if business and (
                endpoint.stage == "T2"
                or endpoint.path
                in {
                    "/monitor",
                    "/auth/school-credential",
                    "/room-preferences/default",
                    "/room-bindings",
                    "/room-candidates/buildings",
                    "/room-candidates/floors",
                    "/room-candidates/rooms",
                    "/room-bindings/{id}",
                }
            ):
                continue
            app.add_api_route(
                f"/api/v1{endpoint.path}",
                unavailable,
                methods=[endpoint.method.upper()],
                name=endpoint.name,
            )
    if business:
        from .business import register

        register(app, service)
    return app
