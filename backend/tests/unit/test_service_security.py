import time
from typing import Annotated
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from services.common.app import create_app
from services.common.runtime import Runtime
from services.common.security import (
    AuthenticationError,
    Principal,
    authorize_owner,
    issue_token,
    require_principal,
    verify_token,
)


def test_signed_context_and_forged_user_header(runtime_factory):
    runtime = runtime_factory()
    owner = uuid4()
    app = create_app("gateway")

    @app.get("/internal/v1/object")
    async def object_(
        principal: Annotated[Principal, Depends(require_principal("foundation:read"))],
    ):
        authorize_owner(principal, owner)
        return {"found": True}

    with TestClient(app) as client:
        assert (
            client.get("/internal/v1/object", headers={"X-User-Id": str(owner)}).status_code == 401
        )
        token = issue_token(
            runtime, "gateway", "foundation:read", uuid4(), user_id=uuid4(), session_version=1
        )
        assert (
            client.get(
                "/internal/v1/object",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-User-Id": str(owner),
                },
            ).status_code
            == 404
        )
        token = issue_token(
            runtime, "gateway", "foundation:read", uuid4(), user_id=owner, session_version=2
        )
        assert (
            client.get(
                "/internal/v1/object",
                headers={
                    "Authorization": f"Bearer {token}",
                },
            ).status_code
            == 200
        )


@pytest.mark.parametrize(
    "change",
    [
        {"exp": 1},
        {"aud": "room"},
        {"iss": "identity"},
        {"sub": "room"},
        {"jti": "not-a-uuid"},
        {"jti": None},
        {"scope": "payment:dispatch"},
        {"user_id": str(uuid4()), "session_version": True},
        {"exp": int(time.time()) + 1000},
    ],
)
def test_reject_invalid_claims(runtime_factory, change):
    runtime = runtime_factory()
    token = issue_token(runtime, "gateway", "foundation:read", uuid4())
    claims = jwt.decode(token, options={"verify_signature": False})
    claims.update(change)
    forged = jwt.encode(
        claims,
        runtime.signing_key.get_secret_value(),
        algorithm="EdDSA",
        headers={"kid": runtime.key_id},
    )
    with pytest.raises(AuthenticationError):
        verify_token(runtime, forged, "foundation:read")


def test_wrong_algorithm_key_and_trust_permission(runtime_factory):
    runtime = runtime_factory()
    token = issue_token(runtime, "gateway", "foundation:read", uuid4())
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode(
        claims,
        "synthetic-hmac-key-of-at-least-32-bytes",
        algorithm="HS256",
        headers={"kid": runtime.key_id},
    )
    with pytest.raises(AuthenticationError):
        verify_token(runtime, forged, "foundation:read")
    document = runtime.model_dump(mode="json")
    document["trust_bundle"][runtime.key_id]["audiences"] = ["identity"]
    restricted = Runtime.model_validate(document)
    with pytest.raises(AuthenticationError):
        verify_token(restricted, token, "foundation:read")
