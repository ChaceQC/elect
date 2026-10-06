"""固定内部目标；认证材料只经验证服务器证书的 TLS 发送。"""

import asyncio
import os
import ssl

import httpx

from .errors import ErrorCode
from .http import ApiError
from .security import issue_token

TARGETS = {
    "identity": "https://identity:8000",
    "school_adapter": "https://school-adapter:8000",
    "room": "http://room:8000",
    "monitoring": "http://monitoring:8000",
    "payment": "http://payment:8000",
}


class ServiceClient:
    def __init__(self, runtime, *, transport=None, local=None):
        self.runtime = runtime
        self.local = local
        self.transport = transport
        self._client = None

    @property
    def client(self):
        if self._client is not None:
            return self._client
        verify = (
            ssl.create_default_context(cafile=os.environ["ELECT_INTERNAL_CA_FILE"])
            if self.transport is None
            else True
        )
        self._client = httpx.AsyncClient(
            verify=verify,
            transport=self.transport,
            trust_env=False,
            timeout=httpx.Timeout(100, connect=3, pool=3),
            limits=httpx.Limits(max_connections=12),
        )
        return self._client

    async def call(
        self, receiver, path, scope, request_id, payload=None, *, principal=None, method="POST",
        budget=None,
    ):
        async with asyncio.timeout(budget):
            return await self._call(receiver, path, scope, request_id, payload,
                                    principal=principal, method=method)

    async def _call(
        self, receiver, path, scope, request_id, payload=None, *, principal=None, method="POST"
    ):
        token = issue_token(
            self.runtime,
            receiver,
            scope,
            request_id,
            user_id=principal.user_id if principal else None,
            session_version=principal.session_version if principal else None,
        )
        if self.local is not None and receiver in self.local.contexts:
            return await self.local.invoke(receiver, path, method, token, payload,
                                           request_id=request_id)
        target = TARGETS[receiver]
        core_url = os.environ.get("ELECT_CORE_URL")
        if core_url and receiver != "school_adapter":
            if core_url != "https://identity:8000":
                raise RuntimeError("核心地址必须使用受验证的内部TLS服务名")
            target = f"{core_url}/domains/{receiver}"
        try:
            response = await self.client.request(
                method,
                target + "/internal/v1" + path,
                headers={"Authorization": f"Bearer {token}", "X-Request-ID": str(request_id)},
                json=payload,
            )
        except httpx.HTTPError:
            raise ApiError(
                503, ErrorCode.DEPENDENCY_UNAVAILABLE, "内部服务暂时不可用，请稍后重试", True
            ) from None
        try:
            value = response.json()
            if not response.is_success:
                error = value["error"]
                raise ApiError(
                    response.status_code,
                    ErrorCode(error["code"]),
                    error["message"],
                    error.get("retryable", False),
                    retry_after_seconds=error.get("retry_after_seconds"),
                    current_version=error.get("current_version"),
                    existing_operation_id=error.get("existing_operation_id"),
                )
            return value
        except (ValueError, KeyError, TypeError):
            raise ApiError(
                503, ErrorCode.DEPENDENCY_UNAVAILABLE, "内部服务响应异常", True
            ) from None

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
