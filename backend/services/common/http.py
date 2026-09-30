"""请求标识和脱敏错误信封。"""

import time
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .errors import ErrorCode
from .ids import new_id
from .logging import log


class ApiError(Exception):
    def __init__(self, status: int, code: ErrorCode, message: str, retryable=False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def metadata(request: Request):
    return {"request_id": request.state.request_id, "server_time": datetime.now(UTC).isoformat()}


def error_response(request: Request, error: ApiError):
    return JSONResponse(
        status_code=error.status,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "retry_after_seconds": None,
                "requires_reauth": False,
                "field_errors": {},
            },
            "meta": metadata(request),
        },
    )


def install_http(app, service: str):
    @app.middleware("http")
    async def request_context(request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        try:
            request.state.request_id = str(UUID(incoming))
        except ValueError:
            request.state.request_id = str(new_id())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            log("request_failed", service=service, request_id=request.state.request_id)
            response = error_response(
                request,
                ApiError(
                    503,
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "服务暂时不可用，请稍后重试",
                    True,
                ),
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        log(
            "request_completed",
            service=service,
            request_id=request.state.request_id,
            status=response.status_code,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return response

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(request, ApiError(422, ErrorCode.INVALID_ARGUMENT, "请求参数不正确"))

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INVALID_ARGUMENT
        return error_response(request, ApiError(exc.status_code, code, "请求无法处理"))
