"""受服务身份保护的内部命令；用户归属须匹配经验证 JWT 上下文。"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator

from .dto import DTO, PositiveMoney, Timestamp, Version
from .events import EVENTS, EventPayload


class UserCommand(DTO):
    owner_user_id: UUID
    request_id: UUID


class AuthenticateLogin(DTO):
    attempt_id: UUID
    browser_nonce_hash: str
    challenge_id: str
    student_id: str
    password: SecretStr
    captcha_answer: str
    request_id: UUID


class StagedCredential(DTO):
    attempt_id: UUID
    credential_ref: UUID
    credential_version: Version
    lookup_aliases: dict[str, str]
    expires_at: Timestamp


class ActivateCredential(UserCommand):
    attempt_id: UUID
    credential_ref: UUID
    expected_credential_version: Version | None


class CredentialResult(DTO):
    credential_ref: UUID
    credential_version: Version
    state: Literal["staged", "active", "revoking", "revoked", "failed"]


class PrepareRetarget(UserCommand):
    operation_id: UUID
    target_binding_id: UUID
    expected_preference_version: Version


class RetargetBarrier(DTO):
    operation_id: UUID
    monitor_id: UUID
    generation: Version
    state: Literal["prepared", "committed", "compensated"]
    cancel_pending: bool
    in_flight_count: int


class CommitRetarget(UserCommand):
    operation_id: UUID
    target_binding_id: UUID
    committed_preference_version: Version


class RevokeCredential(UserCommand):
    operation_id: UUID
    credential_ref: UUID
    expected_credential_version: Version


class RevokeBarrier(RevokeCredential):
    pass


class AuthorizeSend(UserCommand):
    alert_slot_id: UUID
    job_id: UUID
    generation: Version
    email_version: Version
    execution_epoch: Version


class SendPermit(DTO):
    permitted: bool
    permit_id: UUID | None
    expires_at: Timestamp | None
    denial_code: str | None


class DispatchBinding(UserCommand):
    upstream_operation_id: UUID
    candidate_id: str
    credential_ref: UUID
    credential_version: Version


class DispatchOrder(UserCommand):
    upstream_operation_id: UUID
    credential_ref: UUID
    credential_version: Version
    binding_id: UUID
    amount: PositiveMoney
    currency: Literal["CNY"]


class UpstreamResult(DTO):
    upstream_operation_id: UUID
    state: Literal["prepared", "dispatched", "confirmed", "rejected", "reconciling", "unknown"]
    dispatched_at: Timestamp | None
    result_ref: UUID | None
    error_code: str | None


class QueryOperation(UserCommand):
    operation_id: UUID


class PaymentSessionCommand(UserCommand):
    order_id: UUID
    upstream_operation_id: UUID
    step: Literal["E01", "E02", "E03", "E04"]


class SessionIntrospection(DTO):
    session_token: SecretStr
    request_id: UUID


class SessionContext(DTO):
    active: bool
    user_id: UUID | None
    session_version: Version | None
    expires_at: Timestamp | None


class EventEnvelope(DTO):
    event_id: UUID
    type: Literal[
        "credential.updated",
        "credential.revoked",
        "monitor.run_ready",
        "monitor.alert_reserved",
        "notification.delivery_reported",
        "room.history_sync_requested",
        "room.binding_confirmed",
        "payment.order_requested",
        "audit.recorded",
    ]
    schema_version: Literal[1]
    producer: Literal[
        "identity", "school_adapter", "room", "monitoring", "notification", "payment", "gateway"
    ]
    aggregate_id: UUID
    aggregate_version: Version
    occurred_at: Timestamp
    request_id: UUID
    payload: EventPayload
    dedupe_key: Annotated[str, Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def validate_event(self) -> "EventEnvelope":
        if self.type not in EVENTS:
            raise ValueError("未登记的事件类型")
        payload_type, producers = EVENTS[self.type]
        if not isinstance(self.payload, payload_type) or self.producer not in producers:
            raise ValueError("事件载荷/生产者与登记协议不符")
        return self
