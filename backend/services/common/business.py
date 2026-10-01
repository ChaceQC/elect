"""已实现的认证、寝室读取和监控控制；其他业务入口保持关闭。"""

import base64
import os

from redis.asyncio import Redis


def register(app, service):
    if service in {"gateway", "identity", "school_adapter", "room", "monitoring"}:
        from importlib import import_module

        app.include_router(import_module(f"services.{service}.api").router)
    if service == "gateway":
        from services.gateway.monitor_api import router
        from services.gateway.room_api import router as room_router

        app.include_router(router)
        app.include_router(room_router)
        from services.gateway.query_api import router as query_router

        app.include_router(query_router)
    if service == "room":
        from services.room.control_api import router

        app.include_router(router)
        from services.room.query_api import router as query_router

        app.include_router(query_router)
    if service == "school_adapter":
        from services.school_adapter.query_api import router

        app.include_router(router)
    if service == "monitoring":
        from services.monitoring.credential_api import router
        from services.monitoring.permit_api import router as permit_router

        app.include_router(router)
        app.include_router(permit_router)
        from services.monitoring.metrics_api import router as metrics_router
        from services.monitoring.run_api import router as run_router

        app.include_router(run_router)
        app.include_router(metrics_router)
    if service == "identity":
        from services.identity.revocation_api import router

        app.include_router(router)


async def initialize(app, service):
    if service in {"gateway", "identity", "room", "monitoring", "school_adapter", "notification"}:
        from .service_client import ServiceClient

        app.state.service_client = ServiceClient(app.state.runtime)
    if service == "monitoring":
        from services.monitoring.email_crypto import EmailCrypto

        app.state.email_crypto = EmailCrypto.load(os.environ["ELECT_EMAIL_KEY_FILE"])
    if service == "notification":
        from services.notification.email_crypto import EmailCrypto
        from services.notification.smtp import SmtpConfig, SmtpTransport

        from .runtime import side_effect_policy

        app.state.email_crypto = EmailCrypto.load(os.environ["ELECT_EMAIL_KEY_FILE"])
        app.state.smtp = (
            SmtpTransport(SmtpConfig.load(os.environ["ELECT_SMTP_CONFIG_FILE"]))
            if side_effect_policy().real_smtp else None
        )
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
    if getattr(app.state, "history_broker", None):
        await app.state.history_broker.close()
    if hasattr(app.state, "service_client"):
        await app.state.service_client.close()
    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()
