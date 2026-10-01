import hmac
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import (
    BrowserLogin,
    BrowserSession,
    SessionContext,
    SessionIntrospection,
)
from services.common.security import Principal, authorize_owner, require_principal
from services.common.sql import aware, first

from .agreement import agreement
from .dto import Me

router = APIRouter(prefix="/internal/v1")
Browser = Annotated[Principal, Depends(require_principal("identity:browser"))]


async def current_me(app, row, principal):
    user_id = UUID(bytes=row["user_id"])
    context = Principal(principal.service, user_id, row["session_version"], principal.request_id)
    view = await app.state.service_client.call(
        "school_adapter",
        "/credentials/view",
        "credential:read",
        principal.request_id,
        principal=context,
    )
    async with app.state.database.connect() as conn:
        consent = await first(
            conn,
            "SELECT * FROM consents WHERE user_id=:id ORDER BY accepted_at DESC,id DESC LIMIT 1",
            id=user_id.bytes,
        )
        revoke = await first(
            conn,
            "SELECT * FROM credential_operations WHERE owner_user_id=:id "
            "AND state IN ('accepted','running','reconciling','unknown') "
            "ORDER BY created_at DESC LIMIT 1",
            id=user_id.bytes,
        )
    if not consent:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "授权记录暂时不可用", True)
    return Me(
        id=user_id,
        **{**view, **({"credential_status": "revoking"} if revoke else {})},
        csrf_token=row["csrf_token"],
        credential_revoke_operation={
            "id": UUID(bytes=revoke["id"]),
            "type": "credential_revoke",
            "state": revoke["state"],
            "target_binding_id": None,
            "created_at": aware(revoke["created_at"]),
        }
        if revoke
        else None,
        consent={
            "agreement_version": consent["agreement_version"],
            "accepted_at": aware(consent["accepted_at"]),
            "credential_use_allowed": bool(
                consent["credential_use_allowed"] and not consent["revoked_at"]
            ),
            "revoked_at": aware(consent["revoked_at"]),
        },
    )


@router.post("/sessions/introspect")
async def introspect(
    command: SessionIntrospection,
    request: Request,
    principal: Annotated[Principal, Depends(require_principal("session:introspect"))],
):
    row = await request.app.state.app_sessions.context(
        command.session_token.get_secret_value(), required=False
    )
    return SessionContext(
        active=bool(row),
        user_id=UUID(bytes=row["user_id"]) if row else None,
        session_version=row["session_version"] if row else None,
        expires_at=aware(row["expires_at"]) if row else None,
        csrf_token=row["csrf_token"] if row else None,
    )


@router.post("/browser/agreement")
async def get_agreement(principal: Browser):
    return agreement()


@router.post("/browser/login")
async def login(command: BrowserLogin, request: Request, principal: Browser):
    token = await request.app.state.login_saga.login(
        command.login, command.browser_nonce_hash, principal.user_id, principal.request_id
    )
    row = await request.app.state.app_sessions.context(token)
    me = await current_me(request.app, row, principal)
    return {
        "session_token": token,
        "result": {
            "user": me.model_dump(mode="json"),
            "bootstrap": {
                "rooms_state": "loading",
                "requires_binding": None,
                "default_binding_id": None,
                "credential_status": me.credential_status,
            },
        },
    }


@router.post("/browser/me")
async def me(command: BrowserSession, request: Request, principal: Browser):
    row = await request.app.state.app_sessions.context(command.session_token.get_secret_value())
    authorize_owner(principal, UUID(bytes=row["user_id"]))
    return await current_me(request.app, row, principal)


@router.post("/browser/logout")
async def logout(command: BrowserSession, request: Request, principal: Browser):
    row = await request.app.state.app_sessions.context(command.session_token.get_secret_value())
    authorize_owner(principal, UUID(bytes=row["user_id"]))
    if not command.csrf_token or not hmac.compare_digest(command.csrf_token, row["csrf_token"]):
        raise ApiError(403, ErrorCode.CSRF_REJECTED, "请刷新会话后重试")
    await request.app.state.app_sessions.logout(row, principal.request_id)
    return {"revoked": True}
