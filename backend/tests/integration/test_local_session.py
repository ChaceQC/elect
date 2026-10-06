"""R6本库会话：真实MySQL、签名分派/HTTP及Adapter连接失败。"""

import asyncio

import httpx
import pytest
from adapter_process_support import AdapterProcess
from query_resource_support import database, requires_mysql, seed_binding
from test_read_contention import session_fixture

from services.common.app import create_app
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.common.service_client import ServiceClient
from services.common.sql import execute
from services.core.dispatch import Dispatcher

pytestmark = requires_mysql


@pytest.mark.parametrize("direct", [True, False])
def test_local_identity_survives_adapter_failure_and_rejects_revocation(
    runtime_factory, monkeypatch, direct,
):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")
    sender, receiver = runtime_factory("gateway"), runtime_factory("identity")
    receiver.trust_bundle[sender.key_id] = sender.trust_bundle[sender.key_id].model_copy(
        update={"audiences": ["identity"], "scopes": ["identity:browser", "session:introspect"]})

    async def scenario():
        async with database("identity", production_pool=True) as engine:
            sessions, token, owner, sid = await session_fixture(engine)
            async with engine.begin() as conn:
                await execute(conn, "INSERT INTO consents (id,user_id,agreement_version,"
                              "content_hash,accepted_at,credential_use_allowed) VALUES "
                              "(:id,:owner,'synthetic',:hash,UTC_TIMESTAMP(6),1)",
                              id=new_id().bytes, owner=owner.bytes, hash=b"x" * 32)
            identity = create_app("identity", business=True)
            identity.state.runtime = receiver
            identity.state.database = engine
            identity.state.app_sessions = sessions
            attempts = []
            online = False

            def adapter(request):
                attempts.append(request.url.path)
                if not online:
                    raise httpx.ConnectError("synthetic adapter offline", request=request)
                return httpx.Response(200, json={"student_id": "synthetic", "school": "test",
                                               "credential_status": "active",
                                               "credential_version": 1})

            school = ServiceClient(receiver, transport=httpx.MockTransport(adapter))
            identity.state.service_client = school
            service = (ServiceClient(sender, local=Dispatcher({"identity": identity})) if direct
                       else ServiceClient(sender, transport=httpx.ASGITransport(app=identity)))
            gateway = create_app("gateway", business=True)
            gateway.state.service_client = service
            gateway.state.public_origin = "https://elect.example.edu"
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway),
                                             base_url=gateway.state.public_origin) as browser:
                    assert (await browser.get("/api/v1/auth/session")).status_code == 401
                    browser.cookies.set("__Host-elect_session", token)
                    response = await browser.get("/api/v1/auth/session")
                    assert response.status_code == 200
                    local = response.json()["data"]
                    assert set(local) == {"id", "csrf_token", "consent"}
                    assert local["id"] == str(owner) and local["consent"]["credential_use_allowed"]
                    assert attempts == []
                    assert (await browser.get("/api/v1/auth/me")).status_code == 503
                    assert len(attempts) == 1
                    assert (await browser.get("/api/v1/auth/session")).status_code == 200
                    online = True
                    profile = (await browser.get("/api/v1/auth/me")).json()["data"]
                    assert profile["student_id"] == "synthetic" and profile["id"] == str(owner)
                    assert profile["csrf_token"] == local["csrf_token"]
                    # 同一真实token依次验证用户禁用、版本变更、两种到期和撤销。
                    for mutation, restore in [
                        ("UPDATE users SET status='disabled'", "UPDATE users SET status='active'"),
                        ("UPDATE users SET session_version=2",
                         "UPDATE users SET session_version=1"),
                        ("UPDATE app_sessions SET expires_at=UTC_TIMESTAMP(6)",
                         "UPDATE app_sessions SET expires_at="
                         "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 1 HOUR)"),
                        ("UPDATE app_sessions SET absolute_expires_at=UTC_TIMESTAMP(6)",
                         "UPDATE app_sessions SET absolute_expires_at="
                         "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 1 DAY)"),
                        ("UPDATE app_sessions SET revoked_at=UTC_TIMESTAMP(6)",
                         "UPDATE app_sessions SET revoked_at=NULL"),
                    ]:
                        async with engine.begin() as conn:
                            await execute(conn, mutation)
                        assert (await browser.get("/api/v1/auth/session")).status_code == 401
                        async with engine.begin() as conn:
                            await execute(conn, restore)
                    assert (await browser.post("/api/v1/auth/logout", headers={
                        "Origin": gateway.state.public_origin,
                        "X-CSRF-Token": local["csrf_token"],
                    })).status_code == 204
                    browser.cookies.set("__Host-elect_session", token)
                    assert (await browser.get("/api/v1/auth/session")).status_code == 401
                    assert (await browser.get("/api/v1/auth/me")).status_code == 401
            finally:
                await service.close()
                await school.close()

    asyncio.run(scenario())


def test_stopped_adapter_process_keeps_local_identity_and_room_cache(runtime_factory, monkeypatch):
    from services.common.service_client import TARGETS

    sender, identity_runtime, room_runtime = (
        runtime_factory("gateway"), runtime_factory("identity"), runtime_factory("room"))
    for runtime in (identity_runtime, room_runtime):
        runtime.trust_bundle[sender.key_id] = sender.trust_bundle[sender.key_id].model_copy(
            update={"audiences": ["identity", "room"],
                    "scopes": ["identity:browser", "session:introspect", "room:browser"]})

    async def scenario():
        async with database("identity") as identity_db, database("room") as room_db:
            sessions, token, owner, _ = await session_fixture(identity_db)
            binding = new_id()
            await seed_binding(room_db, owner, binding)
            async with identity_db.begin() as conn:
                await execute(conn, "INSERT INTO consents (id,user_id,agreement_version,"
                              "content_hash,accepted_at,credential_use_allowed) VALUES "
                              "(:id,:owner,'synthetic',:hash,UTC_TIMESTAMP(6),1)",
                              id=new_id().bytes, owner=owner.bytes, hash=b"x" * 32)
            async with room_db.begin() as conn:
                await execute(conn, "INSERT INTO room_balance_cache "
                              "(binding_id,balance,source,fetched_at,quality) VALUES "
                              "(:id,12.34,'school_bound_rooms',"
                              "DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 DAY),'fresh')",
                              id=binding.bytes)
            identity = create_app("identity", business=True)
            room = create_app("room", business=True)
            identity.state.runtime, room.state.runtime = identity_runtime, room_runtime
            identity.state.database, room.state.database = identity_db, room_db
            identity.state.app_sessions = sessions
            # 真实TCP调用仅指向本测试子进程，禁止访问学校或业务环境。
            school = ServiceClient(identity_runtime)
            school._client = httpx.AsyncClient(trust_env=False, timeout=2)
            identity.state.service_client = school
            service = ServiceClient(sender, local=Dispatcher({"identity": identity, "room": room}))
            gateway = create_app("gateway", business=True)
            gateway.state.service_client = service
            gateway.state.public_origin = "https://elect.example.edu"
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway),
                                             base_url=gateway.state.public_origin) as browser:
                    browser.cookies.set("__Host-elect_session", token)
                    with AdapterProcess() as process:
                        monkeypatch.setitem(TARGETS, "school_adapter", process.url)
                        assert (await browser.get("/api/v1/auth/me")).status_code == 200
                        process.stop()
                        assert (await browser.get("/api/v1/auth/me")).status_code == 503
                        assert (await browser.get("/api/v1/auth/session")).status_code == 200
                        cached = await browser.get(f"/api/v1/room-bindings/{binding}/balance")
                        assert cached.status_code == 200
                        assert cached.json()["data"]["amount"] == "12.34"
                        assert cached.json()["data"]["stale"] is True
                    with AdapterProcess() as recovered:
                        monkeypatch.setitem(TARGETS, "school_adapter", recovered.url)
                        assert (await browser.get("/api/v1/auth/me")).status_code == 200
                    with pytest.raises(ApiError) as forbidden:
                        await service.call("identity", "/browser/session", "identity:browser",
                                           new_id(), {"session_token": token},
                                           principal=Principal("gateway", new_id(), 1, new_id()))
                    assert forbidden.value.status == 404
                    async with identity_db.begin() as conn:
                        await execute(conn, "RENAME TABLE app_sessions TO unavailable_sessions")
                    assert (await browser.get("/api/v1/auth/session")).status_code == 503
            finally:
                await service.close()
                await school.close()

    asyncio.run(scenario())
