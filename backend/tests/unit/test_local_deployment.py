import asyncio
import base64
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.common.http import install_http
from services.common.runtime import public_origin
from services.deployment.configure_smtp import configure
from services.deployment.smtp_direct_proxy import DirectProxyConfig, authorized
from services.gateway.api import router
from services.notification.smtp import SmtpConfig


@pytest.mark.parametrize("enabled", ["false", "true"])
def test_http_requires_explicit_opt_in_and_exact_private_listener(monkeypatch, enabled):
    monkeypatch.setenv("ELECT_PUBLIC_ORIGIN", "http://10.8.0.88:6874")
    monkeypatch.setenv("ELECT_ALLOW_LOCAL_HTTP", enabled)
    monkeypatch.setenv("ELECT_HTTP_BIND", "10.8.0.88")
    monkeypatch.setenv("ELECT_HTTP_PORT", "6874")
    if enabled == "true":
        assert public_origin() == "http://10.8.0.88:6874"
    else:
        with pytest.raises(ValueError):
            public_origin()


@pytest.mark.parametrize("bind,port,origin", [
    ("0.0.0.0", "6874", "http://0.0.0.0:6874"),
    ("8.8.8.8", "6874", "http://8.8.8.8:6874"),
    ("10.8.0.88", "0", "http://10.8.0.88:0"),
    ("10.8.0.88", "6874", "http://10.8.0.88:6875"),
    ("10.8.0.88", "6874", "http://10.8.0.88:6874/path"),
])
def test_http_rejects_wildcard_public_ip_and_different_origin(monkeypatch, bind, port, origin):
    for key, value in {"ELECT_ALLOW_LOCAL_HTTP": "true", "ELECT_HTTP_BIND": bind,
                       "ELECT_HTTP_PORT": port, "ELECT_PUBLIC_ORIGIN": origin}.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        public_origin()


class IdentityStub:
    def __init__(self):
        self.active = True

    async def call(self, receiver, path, scope, request_id, body=None, **kwargs):
        if path == "/browser/agreement":
            return {"version": "test"}
        if path == "/browser/login":
            return {"result": {}, "session_token": "test-session"}
        if path == "/sessions/introspect":
            assert body["session_token"] == "test-session"
            return {"active": self.active, "user_id": "00000000-0000-0000-0000-000000000001",
                    "session_version": 1, "csrf_token": "test-csrf"}
        if path == "/browser/me":
            assert body["session_token"] == "test-session"
            return {"csrf_token": "test-csrf"}
        if path == "/browser/logout":
            self.active = False
            return {}
        raise AssertionError(path)


@pytest.mark.parametrize("origin,cookie_name,secure", [
    ("http://10.8.0.88:6874", "elect_session_local", False),
    ("https://elect.example.edu", "__Host-elect_session", True),
])
def test_gateway_login_session_origin_csrf_and_logout(origin, cookie_name, secure):
    app = FastAPI()
    app.state.public_origin = origin
    app.state.service_client = IdentityStub()
    install_http(app, "gateway")
    app.include_router(router)
    with TestClient(app, base_url=origin) as client:
        assert client.get("/api/v1/auth/agreement").status_code == 200
        response = client.post("/api/v1/auth/login", headers={"Origin": origin}, json={
            "student_id": "synthetic", "password": "synthetic", "challenge_id": "x" * 43,
            "captcha_answer": "1", "agreement_version": "test", "agreement_accepted": True,
            "credential_use_allowed": True,
        })
        assert response.status_code == 200
        header = response.headers["set-cookie"]
        assert header.startswith(cookie_name + "=")
        assert ("; Secure" in header) is secure
        assert "HttpOnly" in header and "SameSite=lax" in header
        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.post("/api/v1/auth/logout", headers={
            "Origin": "http://other.invalid", "X-CSRF-Token": "test-csrf",
        }).status_code == 403
        assert client.post("/api/v1/auth/logout", headers={"Origin": origin}).status_code == 403
        assert client.post("/api/v1/auth/logout", headers={
            "Origin": origin, "X-CSRF-Token": "test-csrf",
        }).status_code == 204
        assert cookie_name not in client.cookies
        assert client.get("/api/v1/auth/me").status_code == 401


def proxy_config(**changes):
    return DirectProxyConfig(**{
        "host": "smtp.example.invalid", "port": 465, "interface": "eth0",
        "listen_host": "172.17.0.1", "listen_port": 16874, "token": "x" * 43, **changes,
    })


@pytest.mark.parametrize("host", ["0.0.0.0", "10.8.0.88", "8.8.8.8"])
def test_smtp_proxy_cannot_listen_on_external_or_wildcard_address(host):
    with pytest.raises(ValidationError):
        proxy_config(listen_host=host)


@pytest.mark.parametrize("target,token,allowed", [
    ("smtp.example.invalid:465", "x" * 43, True),
    ("smtp.example.invalid:465", "wrong", False),
    ("other.invalid:465", "x" * 43, False),
    ("smtp.example.invalid:587", "x" * 43, False),
])
def test_smtp_proxy_requires_authentication_and_only_one_target(target, token, allowed):
    async def check():
        reader = asyncio.StreamReader()
        auth = base64.b64encode(f"elect:{token}".encode()).decode()
        reader.feed_data((f"CONNECT {target} HTTP/1.1\r\n"
                          f"Proxy-Authorization: Basic {auth}\r\n\r\n").encode())
        reader.feed_eof()
        assert await authorized(reader, proxy_config()) is allowed
    asyncio.run(check())


def test_mail_secret_import_preserves_real_password_and_private_permissions(tmp_path):
    directory = tmp_path / "secrets"
    directory.mkdir(mode=0o700)
    (directory / "smtp_credentials").write_text("{}")
    auth = tmp_path / "auth"
    auth.write_text("sender@example.invalid\nsmtp.example.invalid\n465\nfixture-password\n"
                    "recipient@example.invalid\n")
    configure(SimpleNamespace(directory=directory, email_auth_file=auth, direct_interface=None))
    document = SmtpConfig.model_validate_json((directory / "smtp_credentials").read_text())
    assert document.password.get_secret_value() == "fixture-password"
    assert (directory / "smtp_credentials").stat().st_mode & 0o777 == 0o400
