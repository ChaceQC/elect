import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.common.ids import new_id
from services.common.security import Principal
from services.gateway import api as gateway
from services.identity import api as identity


def test_auth_me_checks_session_once_in_identity(monkeypatch):
    owner = new_id()
    request_id = new_id()
    sessions = SimpleNamespace(context=AsyncMock(return_value={"user_id": owner.bytes}))
    app = SimpleNamespace(state=SimpleNamespace(app_sessions=sessions))
    me = AsyncMock(return_value={"id": str(owner)})
    monkeypatch.setattr(identity, "current_me", me)
    monkeypatch.setattr(gateway, "get_cookie", lambda *args: "x" * 43)
    monkeypatch.setattr(gateway, "success", lambda request, value: value)

    async def call(service, path, scope, rid, payload):
        assert path == "/browser/me" and service == "identity"
        return await identity.me(identity.BrowserSession(**payload),
                                 SimpleNamespace(app=app),
                                 Principal("gateway", None, None, rid))
    client = SimpleNamespace(call=AsyncMock(side_effect=call))
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(request_id)),
                              app=SimpleNamespace(state=SimpleNamespace(service_client=client)))
    assert asyncio.run(gateway.me(request)) == {"id": str(owner)}
    sessions.context.assert_awaited_once()
    client.call.assert_awaited_once()
