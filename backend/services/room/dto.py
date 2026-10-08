from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt

from services.common.dto import (
    DTO,
    ComponentState,
    Count,
    Coverage,
    DateRange,
    Money,
    Page,
    Reading,
    Timestamp,
    Version,
)
from services.common.operations import OperationSummary


class Balance(DTO):
    amount: Money | None
    currency: Literal["CNY"]
    source: Literal["school_bound_rooms", "school_room_candidate"] | None
    fetched_at: Timestamp | None
    school_observed_at: Timestamp | None
    stale: bool
    refresh_state: Literal["idle", "pending", "ready", "failed"]
    error_code: str | None


class Binding(DTO):
    id: UUID
    room_id: UUID
    building: str
    number: str
    display_name: str
    status: Literal["active", "rechecking", "inactive"]
    balance: Balance | None


class Bindings(Page):
    items: list[Binding]
    binding_write_enabled: bool = False
    default_binding_id: UUID | None
    preference_version: Version
    default_switch_operation_id: UUID | None
    binding_removal_operation_id: UUID | None = None
    preference_state: Literal["ready", "switching", "blocked"] = "ready"
    sync_status: ComponentState
    last_synced_at: Timestamp | None
    pending_operations: Annotated[list[OperationSummary], Field(max_length=20)]
    pending_operations_truncated: bool


class Candidate(DTO):
    candidate_id: str
    room_id: str
    building: str
    number: str
    display_name: str
    already_bound: bool
    expires_at: Timestamp


class Candidates(Page):
    items: list[Candidate]
    search_quality: Literal["exact", "partial", "unverified"]
    expires_at: Timestamp


class FilterChoice(DTO):
    id: Annotated[str, Field(min_length=1, max_length=128)]
    label: Annotated[str, Field(min_length=1, max_length=128)]


class FilterChoices(DTO):
    items: Annotated[list[FilterChoice], Field(max_length=1000)]


class BindRequest(DTO):
    candidate_id: Annotated[str, Field(min_length=1, max_length=128)]


class DefaultRequest(DTO):
    binding_id: UUID
    expected_version: Version


class DefaultResult(DTO):
    default_binding_id: UUID
    preference_version: Version
    state: Literal["ready"]


class HistoryRequest(DateRange):
    pass


class Bucket(DateRange):
    amount: Money | None = Field(
        description="按日学校非零金额优先，缺失或零金额以监控余额减少估算补充。"
    )
    energy_usage: Reading | None
    known_days: Count
    expected_days: Annotated[StrictInt, Field(ge=1)]
    complete: bool = Field(description="金额已知日期覆盖全部所选日期，不代表学校结算或估算精度。")
    estimated_amount: Money | None = Field(
        default=None, description="合计中来自余额变化估算的金额。"
    )
    estimated_days: Count = Field(default=0, description="使用余额变化估算的日期数。")


class ConsumptionSummary(DTO):
    amount: Money | None = Field(description="按日去重后的学校金额及监控余额变化估算合计。")
    energy_usage: Reading | None
    known_days: Count
    expected_days: Annotated[StrictInt, Field(ge=1)]
    complete: bool = Field(description="金额已知日期覆盖全部所选日期，不代表学校结算或估算精度。")
    estimated_amount: Money | None = Field(
        default=None, description="合计中来自余额变化估算的金额。"
    )
    estimated_days: Count = Field(default=0, description="使用余额变化估算的日期数。")


class Consumption(DateRange):
    binding_id: UUID
    granularity: Literal["day", "week", "month"]
    buckets: list[Bucket]
    summary: ConsumptionSummary
    coverage: Coverage
    sync_status: ComponentState
    sync_operation: OperationSummary | None
    version: Version
    monitoring_status: Literal["ready", "unavailable"] | None = None


class Profile(DTO):
    student_id: str
    default_binding: Binding | None
    alert_email: str | None


class OverviewSummary(DTO):
    yesterday_amount: Money | None = Field(
        description="总览上海日期范围结束日前一天的合并日金额，与同日曲线一致；未知为null。"
    )
    yesterday_estimated_amount: Money | None = Field(
        default=None, description="昨日金额中来自余额变化估算的金额；0也是有效估算。"
    )
    last_14_days_amount: Money | None
    known_days: Count
    expected_days: Count
    complete: bool = Field(description="金额已知日期覆盖全部所选日期，不代表学校结算或估算精度。")


class MonitorOverview(DTO):
    enabled: bool
    state: Literal["active", "disabled", "requires_reauth", "blocked_room", "retargeting"]
    health: Literal["healthy", "degraded", "unavailable"]
    interval_minutes: Annotated[StrictInt, Field(ge=60, le=1440)]


class Overview(DTO):
    viewing_binding_id: UUID | None
    profile: Profile | None
    balance: Balance | None
    summary: OverviewSummary | None
    daily_consumption: Consumption | None
    monitor: MonitorOverview | None
    component_status: dict[Literal["profile", "balance", "history", "monitor"], ComponentState]
