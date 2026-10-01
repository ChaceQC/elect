"""受服务身份保护的内部命令；用户归属须匹配经验证 JWT 上下文。"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator

from services.identity.dto import LoginRequest

from .dto import DTO, Count, DateRange, Money, PositiveMoney, Timestamp, Version
from .events import EVENTS, EventPayload


class UserCommand(DTO):
    owner_user_id: UUID
    request_id: UUID


class ChallengeCommand(DTO):
    browser_nonce_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class AttemptQuery(DTO):
    attempt_id: UUID


class BrowserLogin(ChallengeCommand):
    login: LoginRequest


class BrowserSession(DTO):
    session_token: SecretStr
    csrf_token: str | None = None


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
    credential_use_allowed: bool


class CredentialResult(DTO):
    credential_ref: UUID
    credential_version: Version
    state: Literal["staged", "active", "revoking", "revoked", "failed"]


class RoomQuery(DTO):
    q: Annotated[str, Field(max_length=128)] = ""
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 10
    room_id: Annotated[str, Field(max_length=128)] | None = None


class OperationQuery(DTO):
    operation_id: UUID


class BindingQuery(DTO):
    binding_id: UUID


class ConsumptionQuery(BindingQuery, DateRange):
    granularity: Literal["day", "week", "month"] = "day"


class HistoryWindowQuery(BindingQuery, DateRange):
    pass


class BalanceObservation(BindingQuery):
    amount: Money
    fetched_at: Timestamp


class SampleQuery(BindingQuery, DateRange):
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 10
    snapshot_token: Annotated[str, Field(min_length=16, max_length=128)] | None = None


class RunQuery(DTO):
    run_id: UUID


class CancelRunQuery(RunQuery):
    expected_version: Version


class RoomFilterQuery(DTO):
    level: Literal["buildings", "floors", "rooms"]
    building_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    floor: Annotated[str, Field(min_length=1, max_length=128)] | None = None

    @model_validator(mode="after")
    def parents(self):
        if self.level != "buildings" and not self.building_id:
            raise ValueError("请选择楼栋")
        if self.level == "rooms" and not self.floor:
            raise ValueError("请选择楼层")
        return self


class CandidateQuery(DTO):
    candidate_id: Annotated[str, Field(min_length=1, max_length=128)]


class SchoolBindingRecord(DTO):
    room_id: Annotated[str, Field(min_length=1, max_length=128)]
    building: str
    number: str
    display_name: str
    meter_code: str | None
    relation_id: str | None
    balance: Money | None


class VerifiedCandidate(DTO):
    record: SchoolBindingRecord
    credential_ref: UUID
    credential_version: Version


class PrepareRetarget(UserCommand):
    operation_id: UUID
    target_binding_id: UUID | None
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
    target_binding_id: UUID | None
    committed_preference_version: Version


class PreferenceProof(DTO):
    operation_id: UUID
    binding_id: UUID | None
    preference_version: Version | None
    committed: bool
    can_compensate: bool


class RevokeCredential(UserCommand):
    operation_id: UUID
    credential_ref: UUID
    expected_credential_version: Version


class RevokeBarrier(RevokeCredential):
    pass


class UpdateCredentialBarrier(UserCommand):
    operation_id: UUID
    credential_ref: UUID
    expected_credential_version: Count


class CredentialProof(DTO):
    credential_ref: UUID | None
    credential_version: Count
    state: Literal["active", "requires_reauth", "revoking", "revoked", "missing"]
    use_allowed: bool


class AuthorizeSend(UserCommand):
    alert_slot_id: UUID
    job_id: UUID
    generation: Version
    email_version: Version
    execution_epoch: Version


class AlertSlotQuery(UserCommand):
    alert_slot_id: UUID


class AlertSnapshot(DTO):
    alert_slot_id: UUID
    eligible: bool
    state: str
    generation: Version
    email_version: Version
    delivery_version: Count
    email: str | None
    binding_id: UUID
    display_name: str | None
    balance: Money
    threshold: PositiveMoney
    captured_at: Timestamp


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
    order_id: UUID
    upstream_operation_id: UUID
    credential_ref: UUID
    credential_version: Version
    binding_id: UUID
    amount: PositiveMoney
    currency: Literal["CNY"]


class DispatchRemoval(UserCommand):
    upstream_operation_id: UUID
    room_operation_id: UUID
    room_id: Annotated[str, Field(min_length=1, max_length=128)]
    credential_ref: UUID
    credential_version: Version
    lease_owner: Annotated[str, Field(min_length=1, max_length=128)]


class RemovalProofQuery(OperationQuery):
    lease_owner: Annotated[str, Field(min_length=1, max_length=128)]


class RemovalProof(DTO):
    room_operation_id: UUID
    upstream_operation_id: UUID
    record: SchoolBindingRecord
    was_default: bool
    expected_preference_version: Version
    credential_ref: UUID
    credential_version: Version
    can_dispatch: bool


class UpstreamResult(DTO):
    upstream_operation_id: UUID
    state: Literal["prepared", "dispatched", "confirmed", "rejected", "reconciling", "unknown"]
    dispatched_at: Timestamp | None
    result_ref: UUID | None
    error_code: str | None
    binding_record: SchoolBindingRecord | None = None


class QueryOperation(UserCommand):
    operation_id: UUID


class PaymentSessionCommand(UserCommand):
    order_id: UUID
    upstream_operation_id: UUID
    step: Literal["E01", "E02", "E03", "E04"]


class OrderQuery(DTO):
    order_id: UUID


class SessionIntrospection(DTO):
    session_token: SecretStr
    request_id: UUID


class SessionContext(DTO):
    active: bool
    user_id: UUID | None
    session_version: Version | None
    expires_at: Timestamp | None
    csrf_token: str | None


class EventEnvelope(DTO):
    event_id: UUID
    type: Literal[
        "credential.updated",
        "credential.revoked",
        "credential.requires_reauth",
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
