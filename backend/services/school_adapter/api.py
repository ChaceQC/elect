from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.internal_dto import (
    ActivateCredential,
    AttemptQuery,
    AuthenticateLogin,
    ChallengeCommand,
    RoomQuery,
)
from services.common.security import (
    Principal,
    authorize_owner,
    require_principal,
    require_user_principal,
)

router = APIRouter(prefix="/internal/v1")
Auth = Annotated[Principal, Depends(require_principal("credential:authenticate"))]


@router.post("/captchas")
async def captcha(
    command: ChallengeCommand,
    request: Request,
    principal: Annotated[Principal, Depends(require_principal("captcha:create"))],
):
    return await request.app.state.school_store.create_challenge(
        command.browser_nonce_hash, request.app.state.school_protocol
    )


@router.post("/login-attempts/authenticate")
async def authenticate(command: AuthenticateLogin, request: Request, principal: Auth):
    return await request.app.state.school_auth.authenticate(command)


@router.post("/login-attempts/status")
async def attempt(command: AttemptQuery, request: Request, principal: Auth):
    return await request.app.state.school_auth.stage_status(command.attempt_id)


@router.post("/credentials/activate")
async def activate(
    command: ActivateCredential,
    request: Request,
    principal: Annotated[Principal, Depends(require_principal("credential:activate"))],
):
    authorize_owner(principal, command.owner_user_id)
    return await request.app.state.school_auth.activate(command)


@router.post("/credentials/view")
async def credential_view(
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("credential:read"))],
):
    row = await request.app.state.school_credentials.current(principal.user_id)
    payload = request.app.state.school_credentials.payload(row)
    return {
        "student_id": payload["student_id"],
        "school": "湖北经济学院",
        "credential_version": row["version"],
        "credential_status": row["status"],
    }


@router.post("/rooms/bound")
async def bindings(
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:rooms"))],
):
    from .infrastructure.rooms import bound_rooms

    value = await request.app.state.school_sessions.read(
        principal.user_id,
        principal.request_id,
        "/base/roomUser/selectRoomListByUserId",
        {},
        include_user=True,
    )
    return {"items": bound_rooms(value)}


@router.post("/rooms/candidates")
async def candidates(
    command: RoomQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:rooms"))],
):
    from .application.candidates import search_candidates

    return await search_candidates(request.app.state, principal, command)
