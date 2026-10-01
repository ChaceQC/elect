"""T2 的路由及领域依赖；未实施的入口保持关闭。"""

import base64
import os

from redis.asyncio import Redis


def register(app, service):
    if service in {"gateway", "identity", "school_adapter", "room"}:
        from importlib import import_module

        app.include_router(import_module(f"services.{service}.api").router)


async def initialize(app, service):
    if service in {"gateway", "identity", "room"}:
        from .service_client import ServiceClient

        app.state.service_client = ServiceClient(app.state.runtime)
    if service == "identity":
        from services.identity.application.login import LoginSaga
        from services.identity.sessions import AppSessions

        from .runtime import read_secret

        pepper = base64.b64decode(
            read_secret(os.environ["ELECT_SESSION_PEPPER_FILE"]), validate=True
        )
        if len(pepper) != 32:
            raise RuntimeError("会话密钥格式错误")
        app.state.app_sessions = AppSessions(app.state.database, pepper)
        app.state.login_saga = LoginSaga(
            app.state.database, app.state.service_client, app.state.app_sessions
        )
    if service == "school_adapter":
        from services.school_adapter.application.authentication import Authentication
        from services.school_adapter.application.sessions import SchoolSessions
        from services.school_adapter.infrastructure.credentials import CredentialRepository
        from services.school_adapter.infrastructure.crypto import EnvelopeCrypto, KeyRing
        from services.school_adapter.infrastructure.protocol import SchoolProtocol
        from services.school_adapter.infrastructure.redis_store import SharedStore
        from services.school_adapter.infrastructure.transport import SchoolTransport

        crypto = EnvelopeCrypto(KeyRing.load(os.environ["ELECT_SCHOOL_KEK_FILE"]))
        lookup = KeyRing.load(os.environ["ELECT_SCHOOL_LOOKUP_FILE"])
        redis = Redis.from_url(
            app.state.runtime.redis_url.get_secret_value(),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        app.state.redis = redis
        store = SharedStore(redis, crypto)
        protocol = SchoolProtocol(SchoolTransport(store))
        repository = CredentialRepository(app.state.database, crypto)
        app.state.school_store, app.state.school_protocol = store, protocol
        app.state.school_credentials = repository
        app.state.school_auth = Authentication(repository, store, protocol, lookup)
        app.state.school_sessions = SchoolSessions(repository, store, protocol, lookup)


async def close(app):
    if hasattr(app.state, "service_client"):
        await app.state.service_client.close()
    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()
