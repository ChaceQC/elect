"""真实领域入口在进程内仍校验服务权限、用户和DTO，且不创建网络客户端。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from services.common.app import create_app
from services.common.domains import CORE_DOMAINS
from services.common.http import ApiError
from services.common.security import Principal
from services.common.service_client import ServiceClient
from services.core.dispatch import Dispatcher


def clients(runtime_factory):
    sender, receiver = runtime_factory("gateway"), runtime_factory("identity")
    entry = sender.trust_bundle[sender.key_id].model_copy(update={
        "audiences": ["identity"], "scopes": ["identity:browser", "session:introspect"],
    })
    receiver.trust_bundle[sender.key_id] = entry
    app = create_app("identity", business=True)
    app.state.runtime = receiver
    app.state.app_sessions = SimpleNamespace(context=AsyncMock(return_value=None))
    dispatcher = Dispatcher({"identity": app})
    return ServiceClient(sender, local=dispatcher), ServiceClient(
        sender, transport=httpx.ASGITransport(app=app)), dispatcher


def test_every_core_endpoint_is_registered():
    dispatcher = Dispatcher(dict.fromkeys(CORE_DOMAINS))
    assert len(dispatcher.routes) == 52
    assert ("monitoring", "POST", "/alert-slots/authorize-send") in dispatcher.routes
    assert ("payment", "POST", "/controls/dispatch-proof") in dispatcher.routes


@pytest.mark.parametrize("path,scope,payload", [
    ("/browser/agreement", "identity:browser", None),
    ("/sessions/introspect", "session:introspect",
     {"session_token": "synthetic-token", "request_id": str(uuid4())}),
    ("/sessions/introspect", "session:introspect", {"unexpected": True}),
    ("/browser/revoke", "identity:browser", {}),
    ("/browser/agreement", "foundation:read", None),
])
def test_direct_result_and_rejections_match_http(runtime_factory, path, scope, payload):
    direct, remote, _ = clients(runtime_factory)
    principal = Principal("gateway", uuid4(), 1, uuid4())

    async def result(client):
        try:
            return await client.call("identity", path, scope, principal.request_id,
                                     payload, principal=principal)
        except ApiError as error:
            return error.status, error.code

    async def verify():
        assert await result(direct) == await result(remote)
        assert direct._client is None
        await remote.close()

    asyncio.run(verify())


def test_direct_does_not_trust_caller_principal_service_or_skip_user(runtime_factory):
    direct, _, dispatcher = clients(runtime_factory)
    receiver = dispatcher.contexts["identity"].state.runtime
    receiver.trust_bundle[direct.runtime.key_id].scopes = ["identity:browser"]

    async def verify():
        with pytest.raises(ApiError) as caught:
            await direct.call("identity", "/browser/revoke", "identity:browser", uuid4(),
                              {"expected_version": 1})
        assert caught.value.status == 404
        # 调用方自己填Principal.service不改变签名issuer，不能伪装其他服务。
        receiver.trust_bundle[direct.runtime.key_id].audiences = ["room"]
        with pytest.raises(ApiError) as caught:
            await direct.call("identity", "/browser/agreement", "identity:browser", uuid4(),
                              principal=Principal("identity", uuid4(), 1, uuid4()))
        assert caught.value.status == 503

    asyncio.run(verify())
