from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr

from services.common.dto import DTO, Timestamp, Version
from services.common.operations import OperationSummary

CredentialStatus = Literal["active", "requires_reauth", "revoking", "revoked", "missing"]


class Agreement(DTO):
    version: str
    content: str
    content_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    updated_at: Timestamp


class CaptchaRequest(DTO):
    previous_challenge_id: str | None = None


class Captcha(DTO):
    challenge_id: Annotated[str, Field(min_length=43, max_length=128)]
    image_data_url: Annotated[str, Field(pattern=r"^data:image/(png|jpeg);base64,")]
    expires_at: Timestamp


class LoginRequest(DTO):
    student_id: Annotated[str, Field(min_length=1, max_length=128)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=1024)]
    challenge_id: Annotated[str, Field(min_length=43, max_length=128)]
    captcha_answer: Annotated[str, Field(min_length=1, max_length=32)]
    agreement_version: str
    agreement_accepted: Literal[True]
    credential_use_allowed: Literal[True]


class Consent(DTO):
    agreement_version: str
    accepted_at: Timestamp
    credential_use_allowed: bool
    revoked_at: Timestamp | None


class Me(DTO):
    id: UUID
    student_id: str
    school: str
    credential_status: CredentialStatus
    credential_version: Version | None
    consent: Consent
    csrf_token: str
    credential_revoke_operation: OperationSummary | None


class Bootstrap(DTO):
    rooms_state: Literal["loading", "ready", "failed"]
    requires_binding: bool | None
    default_binding_id: UUID | None
    credential_status: CredentialStatus


class LoginResult(DTO):
    user: Me
    bootstrap: Bootstrap
