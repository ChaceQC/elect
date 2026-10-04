"""显式一次性 MySQL/Redis 验收；ASGI + 合成上游，没有真实外部业务副作用。"""

import asyncio
import base64
import os
from pathlib import Path
from uuid import UUID

import httpx
from redis.asyncio import Redis

from scripts.t2_fixtures import SyntheticSchool
from services.common.app import create_app
from services.common.config_contract import SideEffectPolicy
from services.common.database import create_database
from services.common.ids import new_id
from services.common.runtime import Runtime, read_secret
from services.common.service_client import ServiceClient
from services.common.sql import execute, first
from services.identity.application.login import LoginSaga
from services.identity.sessions import AppSessions
from services.room.repository import RoomRepository
from services.room.worker import sync_tick
from services.school_adapter.application.authentication import Authentication
from services.school_adapter.application.sessions import SchoolSessions
from services.school_adapter.infrastructure.credentials import CredentialRepository
from services.school_adapter.infrastructure.crypto import EnvelopeCrypto, KeyRing
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.redis_store import SharedStore
from services.school_adapter.infrastructure.transport import SchoolTransport

SERVICES = ["gateway", "identity", "school_adapter", "room", "monitoring", "payment"]


async def fixture_apps():
    apps = {service: create_app(service, business=True) for service in SERVICES}
    for service, app in apps.items():
        runtime = Runtime.model_validate_json(read_secret(f"/run/secrets/{service}_runtime.json"))
        app.state.runtime = runtime
        app.state.public_origin = "https://elect.test.local"
        app.state.side_effect_policy = SideEffectPolicy()
        app.state.database = (
            create_database(runtime.db_url.get_secret_value()) if runtime.db_url else None
        )

    async def dispatch(request):
        name = "school_adapter" if request.url.host == "school-adapter" else request.url.host
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=apps[name]), base_url=str(request.url)
        ) as client:
            return await client.request(
                request.method, str(request.url), headers=request.headers, content=request.content
            )

    for name in SERVICES:
        apps[name].state.service_client = ServiceClient(
            apps[name].state.runtime, transport=httpx.MockTransport(dispatch)
        )
    school = SyntheticSchool()
    adapter = apps["school_adapter"].state
    crypto = EnvelopeCrypto(KeyRing.load("/run/secrets/school_kek_bundle"))
    lookup = KeyRing.load("/run/secrets/school_lookup_hmac_bundle")
    redis = Redis.from_url(adapter.runtime.redis_url.get_secret_value())
    adapter.redis = redis
    store = SharedStore(redis, crypto)
    protocol = SchoolProtocol(
        SchoolTransport(store, transport=httpx.MockTransport(school.handler), resolve=False)
    )
    repository = CredentialRepository(adapter.database, crypto)
    adapter.school_store, adapter.school_protocol, adapter.school_credentials = (
        store,
        protocol,
        repository,
    )
    adapter.school_auth = Authentication(repository, store, protocol, lookup)
    adapter.school_sessions = SchoolSessions(
        repository, store, protocol, lookup, solver=lambda image: "3"
    )
    identity = apps["identity"].state
    from services.monitoring.email_crypto import EmailCrypto

    apps["monitoring"].state.email_crypto = EmailCrypto.load(
        "/run/secrets/monitoring_encryption_key_bundle"
    )
    pepper = base64.b64decode(read_secret("/run/secrets/identity_session_pepper"))
    identity.app_sessions = AppSessions(identity.database, pepper)
    identity.login_saga = LoginSaga(
        identity.database, identity.service_client, identity.app_sessions
    )
    return apps, school


def browser(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://elect.test.local",
        headers={"Origin": "https://elect.test.local"},
    )


async def prepare(client, user, *, password=" synthetic password "):
    policy = (await client.get("/api/v1/auth/agreement")).json()["data"]
    response = await client.post("/api/v1/auth/captcha", json={})
    assert response.status_code == 200, response.status_code
    value = response.json()["data"]
    return {
        "student_id": user,
        "password": password,
        "captcha_answer": "3",
        "challenge_id": value["challenge_id"],
        "agreement_version": policy["version"],
        "agreement_accepted": True,
        "credential_use_allowed": True,
    }


async def login(client, body):
    response = await client.post("/api/v1/auth/login", json=body)
    if response.status_code != 200:
        print("login_failure", response.status_code, response.json().get("error", {}).get("code"))
    assert response.status_code == 200, response.status_code
    value = response.json()["data"]
    assert "synthetic password" not in response.text and "session_token" not in response.text
    client.headers["X-CSRF-Token"] = value["user"]["csrf_token"]
    assert value["bootstrap"]["rooms_state"] == "loading"
    assert (
        "Secure" in response.headers["set-cookie"] and "HttpOnly" in response.headers["set-cookie"]
    )
    return value["user"]


async def verify(apps, school):
    gateway, room, adapter = apps["gateway"], apps["room"], apps["school_adapter"]
    run_id = str(new_id())
    first_name, second_name = f"synthetic-a-{run_id}", f"synthetic-b-{run_id}"
    async with browser(gateway) as first_browser, browser(gateway) as second_browser:
        first_body, second_body = await asyncio.gather(
            prepare(first_browser, first_name), prepare(second_browser, second_name)
        )
        first_user, second_user = await asyncio.gather(
            login(first_browser, first_body), login(second_browser, second_body)
        )
        assert first_user["id"] != second_user["id"]
        assert (await first_browser.get("/api/v1/auth/me")).json()["data"][
            "student_id"
        ] == first_name
        print("两个浏览器的 CAS/nonce/密文/应用 Cookie 隔离：通过")
        responses = await asyncio.gather(
            *(first_browser.post("/api/v1/auth/captcha", json={}) for _ in range(2))
        )
        assert sorted(response.status_code for response in responses) == [200, 400]
        fresh = next(
            response.json()["data"]["challenge_id"]
            for response in responses
            if response.status_code == 200
        )
        stolen = {**second_body, "challenge_id": fresh}
        assert (await second_browser.post("/api/v1/auth/login", json=stolen)).status_code == 400
        wrong = {**first_body, "challenge_id": fresh, "password": "wrong password"}
        assert (await first_browser.post("/api/v1/auth/login", json=wrong)).status_code == 401
        me = (await first_browser.get("/api/v1/auth/me")).json()["data"]
        assert me["credential_version"] == 1 and me["credential_status"] == "active"
        print("Redis 原子刷新、跨 nonce 拒绝、失败密码不覆盖已验证凭据：通过")
        sync_key = str(new_id())
        sync = await first_browser.post(
            "/api/v1/room-bindings/sync", headers={"Idempotency-Key": sync_key}
        )
        assert sync.status_code == 202
        operation = sync.json()["data"]["operation_id"]
        replay = await first_browser.post(
            "/api/v1/room-bindings/sync", headers={"Idempotency-Key": sync_key}
        )
        assert replay.json()["data"]["operation_id"] == operation
        assert (await second_browser.get(f"/api/v1/operations/{operation}")).status_code == 404
        assert await sync_tick(room)
        assert (await first_browser.get(f"/api/v1/operations/{operation}")).json()["data"][
            "state"
        ] == "succeeded"
        listing = (await first_browser.get("/api/v1/room-bindings")).json()["data"]
        assert (
            listing["sync_status"] == "ready"
            and listing["items"][0]["balance"]["amount"] == "25.50"
        )
        assert listing["default_binding_id"] is None
        candidates = (await first_browser.get("/api/v1/room-candidates?q=001")).json()["data"]
        assert (
            candidates["search_quality"] == "unverified" and candidates["items"][0]["already_bound"]
        )
        assert "userName" not in str(candidates) and "住户资料" not in str(candidates)
        print("持久 202、幂等同步、操作越权 404、候选脱敏与默认不提前初始化：通过")
        school.fail_rooms = True
        await first_browser.post(
            "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
        )
        assert await sync_tick(room)
        stale = (await first_browser.get("/api/v1/room-bindings")).json()["data"]
        assert stale["sync_status"] == "stale" and stale["items"][0]["balance"]["amount"] == "25.50"
        school.fail_rooms, school.empty_rooms = False, True
        await first_browser.post(
            "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
        )
        assert await sync_tick(room)
        replaced = (await first_browser.get("/api/v1/room-bindings")).json()["data"]
        assert (
            replaced["sync_status"] == "empty"
            and replaced["items"] == [] and replaced["total"] == 0
        )
        school.empty_rooms = False
        print("学校失败保留余额；成功空列表覆盖当前绑定、保留持久历史：通过")
        assert (
            await first_browser.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"})
        ).status_code == 403
        assert (await first_browser.post("/api/v1/auth/logout")).status_code == 204
        assert (await first_browser.get("/api/v1/auth/me")).status_code == 401
        row = await adapter.state.school_credentials.current(UUID(first_user["id"]))
        assert row["status"] == "active" and row["use_allowed"]
        print("CSRF 拒绝、服务端吊销与退出保留后台授权：通过")
    await verify_crash_and_lease(apps, school)


async def verify_crash_and_lease(apps, school):
    identity, room = apps["identity"], apps["room"]
    async with browser(apps["gateway"]) as client:
        body = await prepare(client, "synthetic-c")
        initial = school.posts
        original = identity.state.service_client.call
        fail = True

        async def crash(receiver, path, *args, **kwargs):
            nonlocal fail
            if path == "/credentials/activate" and fail:
                fail = False
                from services.common.errors import ErrorCode
                from services.common.http import ApiError

                raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "synthetic crash", True)
            return await original(receiver, path, *args, **kwargs)

        identity.state.service_client.call = crash
        response = await client.post("/api/v1/auth/login", json=body)
        assert response.status_code == 503 and "__Host-elect_session" not in response.headers.get(
            "set-cookie", ""
        )
        async with identity.state.database.begin() as conn:
            row = await first(conn, "SELECT id FROM login_attempts WHERE state='activating'")
            await execute(
                conn,
                "UPDATE login_attempts SET updated_at=DATE_SUB(UTC_TIMESTAMP(6),"
                "INTERVAL 10 SECOND),next_reconcile_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=row["id"],
            )
        from services.identity.recovery import recover_tick

        assert await recover_tick(identity)
        user = await login(client, body)
        assert school.posts == initial + 1
        repository = RoomRepository(room.state.database)
        operation = await repository.accept_sync(UUID(user["id"]), str(new_id()))
        old = await repository.claim()
        async with room.state.database.begin() as conn:
            await execute(
                conn,
                "UPDATE room_operations SET lease_until=DATE_SUB(UTC_TIMESTAMP(6),"
                "INTERVAL 1 SECOND) WHERE id=:id",
                id=operation.bytes,
            )
        latest = await repository.claim()
        assert latest and latest["lease_owner"] != old["lease_owner"]
        assert not await repository.complete(old, [], None, new_id())
        assert await repository.complete(latest, [], None, new_id())
        empty = await repository.list(UUID(user["id"]), "", 1, 10)
        assert empty.sync_status == "empty" and not empty.items
        print("激活前崩溃不发 Cookie、无密码恢复且 A03 一次、旧租约拒绝与首次空列表：通过")


async def main():
    from services.common.logging import configure_logging

    configure_logging()
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用显式一次性测试环境")
    apps, school = await fixture_apps()
    try:
        from scripts.t2_safety import verify_shared_limits

        await verify_shared_limits(apps["school_adapter"].state.school_store)
        await verify(apps, school)
    finally:
        for app in apps.values():
            if hasattr(app.state, "service_client"):
                await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()
    print("T2 合成上游 + 实际 MySQL/Redis 验收通过；未访问真实学校")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T2 一次性验收失败（{type(error).__name__}）；检查最后通过步骤") from None
