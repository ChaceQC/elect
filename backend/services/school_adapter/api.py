from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.internal_dto import (
    ActivateCredential,
    AttemptQuery,
    AuthenticateLogin,
    CandidateQuery,
    ChallengeCommand,
    CredentialProof,
    DispatchBinding,
    DispatchRemoval,
    QueryOperation,
    RevokeCredential,
    RoomFilterQuery,
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
    from .credential_control import require_barrier

    await require_barrier(
        request.app,
        principal,
        command.attempt_id,
        command.credential_ref,
        command.expected_credential_version or 0,
        "credential_update",
    )
    return await request.app.state.school_auth.activate(command)


@router.post("/credentials/view")
async def credential_view(
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("credential:read"))],
):
    row = await request.app.state.school_credentials.current(principal.user_id)
    from .credential_control import display_aad

    repository = request.app.state.school_credentials
    if row["status"] == "revoked":
        from uuid import UUID

        student = repository.crypto.open(
            row["account_display"], display_aad(principal.user_id, UUID(bytes=row["id"]))
        )
    else:
        student = repository.payload(row)["student_id"]
    return {
        "student_id": student,
        "school": "湖北经济学院",
        "credential_version": row["version"],
        "credential_status": row["status"],
    }


@router.post("/credentials/control-view", response_model=CredentialProof)
async def control_view(
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("credential:control-read"))],
):
    from .credential_control import proof

    return await proof(request.app.state.school_credentials, principal.user_id)


@router.post("/credentials/revoke")
async def revoke_credential(
    command: RevokeCredential,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("credential:revoke"))],
):
    from .credential_control import require_barrier, revoke

    authorize_owner(principal, command.owner_user_id)
    await require_barrier(
        request.app,
        principal,
        command.operation_id,
        command.credential_ref,
        command.expected_credential_version,
        "credential_revoke",
    )
    return await revoke(
        request.app.state.school_credentials, request.app.state.school_store, command
    )


@router.post("/rooms/bound")
async def bindings(
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:rooms"))],
):
    return await request.app.state.school_sessions.read_bound(
        principal.user_id, principal.request_id,
    )


@router.post("/rooms/candidates")
async def candidates(
    command: RoomQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:rooms"))],
):
    from .application.candidates import search_candidates

    return await search_candidates(request.app.state, principal, command)


@router.post("/rooms/filters")
async def filters(
    command: RoomFilterQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:rooms"))],
):
    from .application.room_filters import filter_choices

    return await filter_choices(request.app.state, principal, command)


@router.post("/rooms/candidate")
async def verify_candidate(
    command: CandidateQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:binding"))],
):
    from .application.binding_candidates import verify_candidate

    return await verify_candidate(request.app.state, principal, command.candidate_id)


@router.post("/upstream/bindings")
async def bind(
    command: DispatchBinding,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:binding"))],
):
    from .application.binding_writes import BindingWrites

    authorize_owner(principal, command.owner_user_id)
    return await BindingWrites(request.app.state).dispatch(command)


@router.post("/upstream/operations")
async def upstream_operation(
    command: QueryOperation,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:binding"))],
):
    from services.common.errors import ErrorCode
    from services.common.http import ApiError
    from services.common.sql import first

    from .application.binding_writes import BindingWrites
    from .application.removal_writes import RemovalWrites

    authorize_owner(principal, command.owner_user_id)
    async with request.app.state.database.connect() as conn:
        row = await first(
            conn,
            "SELECT operation_type FROM upstream_operations WHERE id=:id AND owner_user_id=:owner",
            id=command.operation_id.bytes,
            owner=principal.user_id.bytes,
        )
    if not row or row["operation_type"] not in {"bind_room", "unbind_room"}:
        raise ApiError(404, ErrorCode.NOT_FOUND, "上游操作不存在")
    writes = RemovalWrites if row["operation_type"] == "unbind_room" else BindingWrites
    return await writes(request.app.state).query(
        principal.user_id, command.operation_id, principal.request_id
    )


@router.post("/upstream/removals")
async def removal(
    command: DispatchRemoval,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("school:binding"))],
):
    from .application.removal_writes import RemovalWrites

    authorize_owner(principal, command.owner_user_id)
    return await RemovalWrites(request.app.state).dispatch(command, principal)
