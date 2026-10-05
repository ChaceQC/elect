from typing import Literal
from uuid import UUID

from pydantic import model_validator

from services.common.dto import DTO, Money, PositiveMoney, Timestamp, Version, VersionRequest

OrderState = Literal[
    "created",
    "submitting",
    "awaiting_payment",
    "paid_confirmed",
    "submit_unknown",
    "status_unknown",
    "rejected",
    "expired_confirmed",
    "closed_confirmed",
]
QRStatus = Literal["not_requested", "generating", "ready", "failed", "unknown", "expired_confirmed"]


class OrderReference(DTO):
    order_id: UUID
    binding_id: UUID
    state: OrderState
    amount: Money
    currency: Literal["CNY"]
    created_at: Timestamp


class Capabilities(DTO):
    enabled: bool
    currency: Literal["CNY"]
    min_amount: PositiveMoney
    max_amount: PositiveMoney
    amount_step: PositiveMoney
    unavailable_reason: str | None
    unresolved_order: OrderReference | None
    amount_policy_source: Literal["application_policy"] = "application_policy"


class OrderRequest(DTO):
    binding_id: UUID
    amount: PositiveMoney
    currency: Literal["CNY"] = "CNY"


class AcceptedOrder(DTO):
    order_id: UUID
    state: OrderState
    poll_url: str


class Order(OrderReference):
    version: Version
    cancel_pending: bool = False
    cancelled_at: Timestamp | None = None
    binding_display_name: str
    paid_confirmed: bool
    last_checked_at: Timestamp | None
    qr_status: QRStatus
    qr_expires_at: Timestamp | None
    error_code: str | None
    qr_error_code: str | None = None
    balance_refresh_state: Literal["not_required", "pending", "succeeded", "failed"] = (
        "not_required"
    )
    balance_refresh_operation_id: UUID | None = None

    @model_validator(mode="after")
    def payment_confirmation(self) -> "Order":
        if self.paid_confirmed != (self.state == "paid_confirmed"):
            raise ValueError("付款确认必须与已确认终态一致")
        return self


class OrderCancelRequest(VersionRequest):
    pass


class QRPending(DTO):
    order_id: UUID
    qr_status: QRStatus
    poll_url: str
    retry_after_seconds: int
