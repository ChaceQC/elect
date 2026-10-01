"""Ed25519 单次内部请求身份；对象归属始终单独校验。"""

import time
from dataclasses import dataclass
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import HTTPException, Request

from .errors import ErrorCode
from .http import ApiError
from .ids import new_id


class AuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    service: str
    user_id: UUID | None
    session_version: int | None
    request_id: UUID


def validate_keys(runtime):
    private = serialization.load_pem_private_key(
        runtime.signing_key.get_secret_value().encode(),
        password=None,
    )
    if not isinstance(private, Ed25519PrivateKey):
        raise RuntimeError("服务签名必须是 Ed25519")
    for entry in runtime.trust_bundle.values():
        if not isinstance(
            serialization.load_pem_public_key(entry.public_key.encode()), Ed25519PublicKey
        ):
            raise RuntimeError("服务验证密钥必须是 Ed25519")
    actual = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    registered = serialization.load_pem_public_key(
        runtime.trust_bundle[runtime.key_id].public_key.encode(),
    ).public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if actual != registered:
        raise RuntimeError("服务签名密钥与 trust bundle 不匹配")


def issue_token(runtime, audience, scope, request_id, *, user_id=None, session_version=None):
    now = int(time.time())
    claims = {
        "iss": runtime.service,
        "sub": runtime.service,
        "aud": audience,
        "iat": now,
        "exp": now + 60,
        "jti": str(new_id()),
        "scope": scope,
        "request_id": str(request_id),
    }
    if user_id is not None:
        if type(session_version) is not int or session_version < 1:
            raise ValueError("用户上下文必须携带会话版本")
        claims.update(user_id=str(user_id), session_version=session_version)
    return jwt.encode(
        claims,
        runtime.signing_key.get_secret_value(),
        algorithm="EdDSA",
        headers={"kid": runtime.key_id, "typ": "JWT"},
    )


def verify_token(runtime, token, scope) -> Principal:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "EdDSA" or header.get("typ") != "JWT":
            raise ValueError("algorithm")
        entry = runtime.trust_bundle[header["kid"]]
        claims = jwt.decode(
            token,
            entry.public_key,
            algorithms=["EdDSA"],
            audience=runtime.service,
            issuer=entry.issuer,
            options={"require": ["iss", "sub", "aud", "iat", "exp", "jti", "scope", "request_id"]},
        )
        if claims["sub"] != entry.issuer or claims["aud"] != runtime.service:
            raise ValueError("identity")
        if runtime.service not in entry.audiences or scope not in entry.scopes:
            raise ValueError("permission")
        if claims["scope"] != scope:
            raise ValueError("scope")
        if type(claims["exp"]) is not int or type(claims["iat"]) is not int:
            raise ValueError("time_type")
        if not 0 < claims["exp"] - claims["iat"] <= 60:
            raise ValueError("ttl")
        UUID(claims["jti"])
        request_id = UUID(claims["request_id"])
        user = UUID(claims["user_id"]) if "user_id" in claims else None
        version = claims.get("session_version")
        if (user is None and version is not None) or (
            user is not None and (type(version) is not int or version < 1)
        ):
            raise ValueError("user_context")
        return Principal(entry.issuer, user, version, request_id)
    except Exception:
        raise AuthenticationError("服务身份或权限无效") from None


def require_principal(scope):
    async def dependency(request: Request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401)
        try:
            principal = verify_token(request.app.state.runtime, authorization[7:], scope)
        except AuthenticationError:
            raise HTTPException(401) from None
        # 传播已签名的关联 ID，不以任意用户头部构建上下文。
        request.state.request_id = str(principal.request_id)
        return principal

    return dependency


def authorize_owner(principal: Principal, owner_user_id: UUID):
    if principal.user_id is None or principal.user_id != owner_user_id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "对象不存在")


def require_user_principal(scope):
    verified = require_principal(scope)

    async def dependency(request: Request):
        principal = await verified(request)
        if principal.user_id is None:
            raise ApiError(404, ErrorCode.NOT_FOUND, "对象不存在")
        return principal

    return dependency
