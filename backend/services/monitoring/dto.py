from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, field_validator, model_validator

from services.common.dto import DTO, Count, Money, Page, PositiveMoney, Reading, Timestamp, Version

MonitorState = Literal["active", "disabled", "requires_reauth", "blocked_room", "retargeting"]
RunState = Literal[
    "pending",
    "running",
    "retry_wait",
    "cancel_requested",
    "succeeded",
    "failed",
    "cancelled",
]
Interval = Annotated[StrictInt, Field(ge=60, le=1440)]
RepeatLimit = Annotated[StrictInt, Field(ge=1, le=5)]


def non_nullable_patch(schema: dict) -> None:
    """字段省略保持原值；显式 null 不属于这些字段的协议。"""
    alternatives = schema.pop("anyOf", [])
    for alternative in alternatives:
        if alternative.get("type") != "null":
            schema.update(alternative)
    schema.pop("default", None)


class MonitorConfig(DTO):
    enabled: bool
    interval_minutes: Interval
    repeat_limit: RepeatLimit
    threshold: PositiveMoney
    email: str | None


class MonitorPatch(DTO):
    expected_version: Version
    enabled: bool | None = Field(default=None, json_schema_extra=non_nullable_patch)
    interval_minutes: Interval | None = Field(default=None, json_schema_extra=non_nullable_patch)
    repeat_limit: RepeatLimit | None = Field(default=None, json_schema_extra=non_nullable_patch)
    threshold: PositiveMoney | None = Field(default=None, json_schema_extra=non_nullable_patch)
    email: str | None = None

    @field_validator("threshold")
    @classmethod
    def threshold_limit(cls, value: str | None) -> str | None:
        if value is not None and Decimal(value) > Decimal("10000.00"):
            raise ValueError("阈值不得超过 10000.00")
        return value

    @model_validator(mode="after")
    def patch_fields(self) -> "MonitorPatch":
        for key in self.model_fields_set - {"email"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} 不允许 null；省略表示保持原值")
        if self.email is not None and (
            "\r" in self.email or "\n" in self.email or "@" not in self.email
        ):
            raise ValueError("邮箱格式无效")
        return self


class NotificationSummary(DTO):
    state: Literal[
        "idle", "pending", "sending", "sent", "email_failed", "delivery_unknown", "cancelled"
    ]
    last_sent_at: Timestamp | None
    last_error_code: str | None
    next_retry_at: Timestamp | None
    in_flight_count: Count
    delivery_unknown_count: Count


class RunAttempt(DTO):
    attempt_no: Version
    started_at: Timestamp
    finished_at: Timestamp | None
    outcome: Literal["running", "succeeded", "retryable", "failed", "cancelled", "fenced"]
    error_code: str | None


class Run(DTO):
    id: UUID
    version: Version
    binding_id: UUID
    state: RunState
    scheduled_for: Timestamp
    started_at: Timestamp | None
    finished_at: Timestamp | None
    next_attempt_at: Timestamp | None
    cancel_pending: bool
    error_code: str | None
    attempts: list[RunAttempt]


class AcceptedRun(DTO):
    run_id: UUID
    version: Version
    state: RunState
    poll_url: str


class Monitor(DTO):
    id: UUID | None
    binding_id: UUID | None
    config: MonitorConfig
    state: MonitorState
    health: Literal["healthy", "degraded", "unavailable"]
    version: Version
    generation: Version
    current_run: Run | None
    last_run: Run | None
    next_run_at: Timestamp | None
    last_success_at: Timestamp | None
    last_error_code: str | None
    cancel_pending: bool
    in_flight_count: Count
    notification: NotificationSummary


class Sample(DTO):
    id: UUID
    run_id: UUID
    captured_at: Timestamp
    balance: Money
    previous_captured_at: Timestamp | None
    balance_delta: Money | None
    balance_delta_kind: Literal["net_balance_change"]
    gap_seconds: Count | None
    gap_detected: bool
    meter_last_reading: Reading | None
    meter_reading: Reading | None
    meter_delta: Reading | None
    meter_record_date: date | None
    meter_source: Literal["school_C02_daily_record"] | None
    meter_source_record_key: str | None
    meter_is_repeated: bool
    quality: Literal[
        "balance_only", "meter_not_realtime", "meter_inconsistent", "meter_negative_delta"
    ]


class Samples(Page):
    items: list[Sample]
    has_monitor_history: bool
    snapshot_token: str
    snapshot_expires_at: Timestamp
