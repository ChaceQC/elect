"""所有公开 DTO 使用的协议原语。"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    model_validator,
)

from .errors import ErrorCode


def positive_money(value: str) -> str:
    if Decimal(value) <= 0:
        raise ValueError("金额必须大于零")
    return value


Money = Annotated[str, Field(pattern=r"^-?(0|[1-9]\d{0,11})\.\d{2}$")]
PositiveMoney = Annotated[
    str, Field(pattern=r"^(0|[1-9]\d{0,11})\.\d{2}$"), AfterValidator(positive_money)
]
Reading = Annotated[str, Field(pattern=r"^-?(0|[1-9]\d{0,13})\.\d{4}$")]
Version = Annotated[StrictInt, Field(ge=1)]
Count = Annotated[StrictInt, Field(ge=0)]
Timestamp = AwareDatetime
Coverage = Literal["complete", "partial", "unknown"]
ComponentState = Literal["ready", "loading", "empty", "stale", "partial", "failed", "unavailable"]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(DTO):
    request_id: UUID
    server_time: Timestamp


class Error(DTO):
    code: ErrorCode
    message: str
    retryable: bool
    retry_after_seconds: Count | None
    requires_reauth: bool
    field_errors: dict[str, str]
    current_version: Version | None = None
    existing_operation_id: UUID | None = None


class ErrorEnvelope(DTO):
    error: Error
    meta: Meta


class VersionRequest(DTO):
    expected_version: Version


class DateRange(DTO):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_range(self) -> "DateRange":
        days = (self.end_date - self.start_date).days + 1
        if not 1 <= days <= 366:
            raise ValueError("日期范围须按上海日期含首尾，且不超过 366 天")
        return self


class Page(DTO):
    page: Annotated[StrictInt, Field(ge=1)]
    page_size: Annotated[StrictInt, Field(ge=1, le=100)]
    total: Count
