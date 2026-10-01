"""固定内部目标；认证材料只经验证服务器证书的 TLS 发送。"""

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
}


class ServiceClient:
    def __init__(self, runtime, *, transport=None):
        self.runtime = runtime
        verify = (
            ssl.create_default_context(cafile=os.environ["ELECT_INTERNAL_CA_FILE"])
            if transport is None
            else True
        )
        self.client = httpx.AsyncClient(
            verify=verify,
            transport=transport,
            trust_env=False,
            timeout=httpx.Timeout(100, connect=3, pool=3),
            limits=httpx.Limits(max_connections=12),
        )

    async def call(
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
        try:
            response = await self.client.request(
                method,
                TARGETS[receiver] + "/internal/v1" + path,
                headers={"Authorization": f"Bearer {token}"},
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
        await self.client.aclose()
