import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, Response

from services.common.browser_security import require_browser_write, require_origin
from services.common.dto import VersionRequest
from services.common.errors import ErrorCode
from services.common.http import ApiError, metadata
from services.common.security import Principal
from services.identity.dto import CaptchaRequest, LoginRequest
from services.school_adapter.infrastructure.redis_store import browser_hash

router = APIRouter(prefix="/api/v1")
SESSION_COOKIE = "__Host-elect_session"
NONCE_COOKIE = "__Host-elect_browser"


def success(request, value, *, status=200):
    return JSONResponse({"data": value, "meta": metadata(request)}, status_code=status)


def cookie(response, name, value, age):
    response.set_cookie(
        name, value, max_age=age, secure=True, httponly=True, samesite="lax", path="/"
    )


async def session(request, *, required=True):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        if required:
            raise ApiError(401, ErrorCode.APP_SESSION_EXPIRED, "请先登录应用")
        return None, None
    value = await request.app.state.service_client.call(
        "identity",
        "/sessions/introspect",
        "session:introspect",
        UUID(request.state.request_id),
        {"session_token": token, "request_id": request.state.request_id},
    )
    if not value["active"]:
        if required:
            raise ApiError(401, ErrorCode.APP_SESSION_EXPIRED, "应用会话已过期，请重新登录")
        return None, None
    return Principal(
        "gateway", UUID(value["user_id"]), value["session_version"], UUID(request.state.request_id)
    ), value["csrf_token"]


@router.get("/auth/agreement")
async def agreement(request: Request):
    value = await request.app.state.service_client.call(
        "identity", "/browser/agreement", "identity:browser", UUID(request.state.request_id)
    )
    response = success(request, value)
    if len(request.cookies.get(NONCE_COOKIE, "")) != 43:
        cookie(response, NONCE_COOKIE, secrets.token_urlsafe(32), 600)
    return response


@router.post("/auth/captcha")
async def captcha(command: CaptchaRequest, request: Request):
    require_origin(request)
    nonce = request.cookies.get(NONCE_COOKIE)
    if not nonce or len(nonce) != 43:
        nonce = secrets.token_urlsafe(32)
    value = await request.app.state.service_client.call(
        "school_adapter",
        "/captchas",
        "captcha:create",
        UUID(request.state.request_id),
        {"browser_nonce_hash": browser_hash(nonce)},
    )
    response = success(request, value)
    cookie(response, NONCE_COOKIE, nonce, 600)
    return response


@router.post("/auth/login")
async def login(command: LoginRequest, request: Request):
    require_origin(request)
    principal, csrf = await session(request, required=False)
    if principal:
        require_browser_write(request, csrf)
    body = command.model_dump(mode="json")
    body["password"] = command.password.get_secret_value()
    value = await request.app.state.service_client.call(
        "identity",
        "/browser/login",
        "identity:browser",
        UUID(request.state.request_id),
        {"login": body, "browser_nonce_hash": browser_hash(request.cookies.get(NONCE_COOKIE))},
        principal=principal,
    )
    response = success(request, value["result"])
    cookie(response, SESSION_COOKIE, value["session_token"], 7 * 86400)
    return response


@router.get("/auth/me")
async def me(request: Request):
    principal, _ = await session(request)
    value = await request.app.state.service_client.call(
        "identity",
        "/browser/me",
        "identity:browser",
        principal.request_id,
        {"session_token": request.cookies[SESSION_COOKIE]},
        principal=principal,
    )
    return success(request, value)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request):
    require_origin(request)
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    await request.app.state.service_client.call(
        "identity",
        "/browser/logout",
        "identity:browser",
        principal.request_id,
        {"session_token": request.cookies[SESSION_COOKIE], "csrf_token": csrf},
        principal=principal,
    )
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    return response


@router.get("/room-bindings")
async def bindings(
    request: Request,
    q: str = Query("", max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    principal, _ = await session(request)
    value = await request.app.state.service_client.call(
        "room",
        "/browser/bindings",
        "room:browser",
        principal.request_id,
        {"q": q, "page": page, "page_size": page_size},
        principal=principal,
    )
    return success(request, value)


@router.post("/room-bindings/sync", status_code=202)
async def sync(
    request: Request, idempotency_key: Annotated[str, Header(min_length=16, max_length=128)]
):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await request.app.state.service_client.call(
        "room",
        "/browser/sync",
        "room:browser",
        principal.request_id,
        {"idempotency_key": idempotency_key},
        principal=principal,
    )
    return success(request, value, status=202)


@router.get("/room-candidates")
async def candidates(
    request: Request,
    q: str = Query("", max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    room_id: str | None = Query(None, max_length=128),
):
    principal, _ = await session(request)
    value = await request.app.state.service_client.call(
        "room",
        "/browser/candidates",
        "room:browser",
        principal.request_id,
        {"q": q, "page": page, "page_size": page_size, "room_id": room_id},
        principal=principal,
    )
    return success(request, value)


@router.get("/operations/{id}")
async def operation(id: UUID, request: Request):
    principal, _ = await session(request)
    for receiver in ["room", "identity", "payment"]:
        try:
            value = await request.app.state.service_client.call(
                receiver,
                "/browser/operation",
                f"{receiver}:browser",
                principal.request_id,
                {"operation_id": str(id)},
                principal=principal,
            )
            return success(request, value)
        except ApiError as error:
            if error.status != 404:
                raise
    raise ApiError(404, ErrorCode.NOT_FOUND, "操作不存在")


@router.delete("/auth/school-credential", status_code=202)
async def revoke_credential(command: VersionRequest, request: Request):
    principal, csrf = await session(request)
    require_browser_write(request, csrf)
    value = await request.app.state.service_client.call(
        "identity",
        "/browser/revoke",
        "identity:browser",
        principal.request_id,
        command.model_dump(),
        principal=principal,
    )
    return success(request, value, status=202)
