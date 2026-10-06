"""直接调用既有领域入口，保留身份依赖和DTO；不经过HTTP或JSON字节往返。"""

import asyncio
import time
from copy import deepcopy
from uuid import UUID

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from pydantic import TypeAdapter
from starlette.exceptions import HTTPException

from services.common.business import routers
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.logging import log_failure


class Dispatcher:
    def __init__(self, contexts):
        self.contexts = contexts
        self.routes = {}
        for domain in contexts:
            for router in routers(domain):
                for route in router.routes:
                    self.register(domain, route)

    def register(self, domain, route):
        # 当前内部协议仅允许静态路径、一个DTO与一个身份依赖；新增形式必须显式适配。
        if not isinstance(route, APIRoute):
            raise RuntimeError("核心内部路由必须直接声明")
        dep = route.dependant
        if (dep.path_params or dep.query_params or dep.header_params or dep.cookie_params
                or len(dep.body_params) > 1 or len(dep.dependencies) != 1
                or dep.dependencies[0].name != "principal"
                or dep.dependencies[0].dependencies):
            raise RuntimeError("核心内部路由依赖不受支持")
        for method in route.methods:
            key = (domain, method, route.path.removeprefix("/internal/v1"))
            if key in self.routes:
                raise RuntimeError("核心内部路由重复")
            self.routes[key] = route

    async def invoke(self, domain, path, method, token, payload, *, request_id=None):
        route = self.routes.get((domain, method, path))
        if route is None:
            raise ApiError(404, ErrorCode.NOT_FOUND, "内部接口不存在")
        request = Request({"type": "http", "app": self.contexts[domain],
                           "method": method, "path": "/internal/v1" + path,
                           "headers": [(b"authorization", f"Bearer {token}".encode())],
                           "query_string": b""})
        try:
            request.state.request_id = str(UUID(str(request_id)))
        except ValueError:
            request.state.request_id = str(new_id())
        started = time.monotonic()
        try:
            async with asyncio.timeout(100):
                return await self.execute(route, request, payload)
        except ApiError:
            raise
        except HTTPException as error:
            # 与ServiceClient的HTTP认证错误处理一致；不泄露内部认证细节。
            raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE,
                           "内部服务响应异常", True) from error
        except Exception as error:
            log_failure("dispatch_failed", error, service="core", domain=domain,
                        route=route.name, request_id=request.state.request_id,
                        duration_ms=round((time.monotonic() - started) * 1000))
            raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE,
                           "内部服务暂时不可用，请稍后重试", True) from None

    async def execute(self, route, request, payload):
        dep = route.dependant
        values = {"principal": await dep.dependencies[0].call(request)}
        if dep.request_param_name:
            values[dep.request_param_name] = request
        for field in dep.body_params:
            value, errors = field.validate(deepcopy(payload), {}, loc=("body",))
            if errors:
                missing_version = any(error["type"] == "missing"
                                      and error["loc"][-1] == "expected_version"
                                      for error in errors)
                raise ApiError(428 if missing_version else 422,
                               ErrorCode.PRECONDITION_REQUIRED if missing_version
                               else ErrorCode.INVALID_ARGUMENT, "请求参数不正确")
            values[field.name] = value
        result = await route.endpoint(**values)
        if route.response_model:
            result = TypeAdapter(route.response_model).validate_python(result)
        # 调用方仍接收原协议字典；UUID/Decimal/日期按DTO规则转换，避免共享可变对象。
        return deepcopy(jsonable_encoder(result))
