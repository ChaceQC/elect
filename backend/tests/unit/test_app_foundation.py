from uuid import UUID

from fastapi import Request
from fastapi.responses import Response
from fastapi.testclient import TestClient

from services.common.app import create_app
from services.common.browser_security import require_browser_write
from services.common.http import metadata
from services.common.runtime import load_runtime


def test_health_and_closed_business_routes(runtime_factory):
    runtime_factory()
    with TestClient(create_app("gateway")) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").json()["business_enabled"] is False
        response = client.get("/api/v1/auth/me", headers={"X-Request-ID": "forged\nvalue"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FEATURE_DISABLED"
        assert str(UUID(response.headers["X-Request-ID"])) == response.json()["meta"]["request_id"]
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/unknown").json()["error"]["code"] == "NOT_FOUND"


def test_raw_failures_and_validation_inputs_are_redacted(runtime_factory):
    runtime_factory()
    app = create_app("gateway")

    @app.get("/test-failure")
    async def failure():
        raise RuntimeError("mysql://root:private-password@host/database")

    @app.get("/test-validated")
    async def validated(request: Request, value: int):
        return {"data": value, "meta": metadata(request)}

    with TestClient(app) as client:
        failed = client.get("/test-failure")
        assert failed.status_code == 503
        assert "private-password" not in failed.text
        invalid = client.get("/test-validated?value=private-password")
        assert invalid.status_code == 422
        assert "private-password" not in invalid.text


def test_bad_runtime_is_redacted(tmp_path, monkeypatch):
    path = tmp_path / "runtime"
    path.write_text('{"db_url":"mysql://root:private-password@host/database"}')
    monkeypatch.setenv("ELECT_RUNTIME_FILE", str(path))
    try:
        load_runtime("identity")
    except RuntimeError as error:
        assert "private-password" not in str(error)
    else:
        raise AssertionError("非法 Secret 未被拒绝")


def test_origin_and_session_csrf_are_both_required(runtime_factory):
    runtime_factory()
    app = create_app("gateway")

    @app.post("/test-write")
    async def write(request: Request):
        require_browser_write(request, "test-session-csrf")
        return Response(status_code=204)

    with TestClient(app) as client:
        assert (
            client.post(
                "/test-write",
                headers={
                    "Origin": "https://foreign.example.edu",
                    "X-CSRF-Token": "test-session-csrf",
                },
            ).json()["error"]["code"]
            == "ORIGIN_REJECTED"
        )
        assert (
            client.post(
                "/test-write",
                headers={
                    "Origin": "https://elect.example.edu",
                },
            ).json()["error"]["code"]
            == "CSRF_REJECTED"
        )
        response = client.post(
            "/test-write",
            headers={
                "Origin": "https://elect.example.edu",
                "X-CSRF-Token": "test-session-csrf",
            },
        )
        assert response.status_code == 204 and response.content == b""
