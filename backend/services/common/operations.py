from typing import Literal
from uuid import UUID

from .dto import DTO, Timestamp

OperationType = Literal[
    "credential_revoke",
    "binding_sync",
    "bind_room",
    "switch_default",
    "balance_refresh",
    "history_sync",
    "qr_refresh",
]
OperationState = Literal[
    "accepted",
    "running",
    "reconciling",
    "unknown",
    "succeeded",
    "failed",
    "cancelled",
]


class OperationSummary(DTO):
    id: UUID
    type: OperationType
    state: OperationState
    target_binding_id: UUID | None
    created_at: Timestamp


class Operation(OperationSummary):
    binding_status: Literal["pending", "confirmed", "failed", "unknown"] | None
    default_status: Literal["pending", "switching", "confirmed", "unchanged", "failed"] | None
    retryable: bool
    error_code: str | None
    next_reconcile_at: Timestamp | None
    result_binding_id: UUID | None
    result_order_id: UUID | None


class AcceptedOperation(DTO):
    operation_id: UUID
    state: OperationState
    poll_url: str
