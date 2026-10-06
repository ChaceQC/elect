"""已实现的认证、寝室读取和监控控制；其他业务入口保持关闭。"""

import base64
import os


def routers(service):
    from importlib import import_module

    modules = {
        "gateway": ("api", "monitor_api", "room_api", "query_api", "payment_api"),
        "identity": ("api", "revocation_api"),
        "room": ("api", "control_api", "query_api"),
        "school_adapter": ("api", "query_api", "payment_api"),
        "monitoring": ("api", "credential_api", "permit_api", "run_api", "metrics_api"),
        "payment": ("api",),
    }
    return [import_module(f"services.{service}.{module}").router
            for module in modules.get(service, ())]


def register(app, service):
    for router in routers(service):
        app.include_router(router)


async def initialize(app, service):
    if service in {
        "gateway",
        "identity",
        "room",
        "monitoring",
        "school_adapter",
        "notification",
        "payment",
    }:
        from .service_client import ServiceClient

        factory = getattr(app.state, "service_client_factory", ServiceClient)
        app.state.service_client = factory(app.state.runtime)
    if service == "monitoring":
        from services.monitoring.email_crypto import EmailCrypto

        app.state.email_crypto = EmailCrypto.load(secret_file(app, "ELECT_EMAIL_KEY_FILE"))
    if service == "notification":
        from services.notification.email_crypto import EmailCrypto
        from services.notification.smtp import SmtpConfig, SmtpTransport

        from .runtime import side_effect_policy

        app.state.email_crypto = EmailCrypto.load(secret_file(app, "ELECT_EMAIL_KEY_FILE"))
        app.state.smtp = (
            SmtpTransport(SmtpConfig.load(os.environ["ELECT_SMTP_CONFIG_FILE"]))
            if getattr(app.state, "mail_sender", True) and side_effect_policy().real_smtp
            else None
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
        from redis.asyncio import Redis

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
        control = getattr(app.state, "process_control", None)
        if control:
            executor = app.state.school_sessions.ocr_executor
            control.watch(service, "ocr", executor.health_failure)
            control.callbacks.append(executor.request_stop)


def secret_file(app, name):
    files = getattr(app.state, "secret_files", {})
    return files[name] if name in files else os.environ[name]


async def close(app):
    if hasattr(app.state, "school_sessions"):
        drained = await app.state.school_sessions.ocr_executor.close()
        control = getattr(app.state, "process_control", None)
        if not drained and control:
            control.fail("school_adapter", "ocr", "OCR_DRAIN_EXHAUSTED", exhausted=True)
    if getattr(app.state, "payment_broker", None):
        await app.state.payment_broker.close()
    if getattr(app.state, "history_broker", None):
        await app.state.history_broker.close()
    if hasattr(app.state, "service_client"):
        await app.state.service_client.close()
    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()
