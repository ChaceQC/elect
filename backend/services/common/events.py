from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from .dto import DTO, Version


class CredentialPayload(DTO):
    credential_id: UUID
    owner_user_id: UUID
    credential_version: Version


class RunReadyPayload(DTO):
    run_id: UUID
    generation: Version


class AlertReservedPayload(DTO):
    alert_slot_id: UUID
    owner_user_id: UUID
    generation: Version
    email_version: Version


class DeliveryReportedPayload(DTO):
    job_id: UUID
    alert_slot_id: UUID
    state: Literal["sent", "failed", "delivery_unknown", "cancelled"]


class HistorySyncPayload(DTO):
    sync_id: UUID
    binding_id: UUID


class BindingConfirmedPayload(DTO):
    binding_id: UUID
    owner_user_id: UUID
    preference_version: Version


class OrderRequestedPayload(DTO):
    order_id: UUID
    owner_user_id: UUID


class AuditPayload(DTO):
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
    object_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
    object_id: UUID
    result: Literal["succeeded", "failed", "denied", "cancelled", "unknown"]
    actor_user_id: UUID | None = None


EventPayload = (
    CredentialPayload
    | RunReadyPayload
    | AlertReservedPayload
    | DeliveryReportedPayload
    | HistorySyncPayload
    | BindingConfirmedPayload
    | OrderRequestedPayload
    | AuditPayload
)

EVENTS = {
    "credential.updated": (CredentialPayload, ("school_adapter",)),
    "credential.revoked": (CredentialPayload, ("school_adapter",)),
    "monitor.run_ready": (RunReadyPayload, ("monitoring",)),
    "monitor.alert_reserved": (AlertReservedPayload, ("monitoring",)),
    "notification.delivery_reported": (DeliveryReportedPayload, ("notification",)),
    "room.history_sync_requested": (HistorySyncPayload, ("room",)),
    "room.binding_confirmed": (BindingConfirmedPayload, ("room",)),
    "payment.order_requested": (OrderRequestedPayload, ("payment",)),
    "audit.recorded": (
        AuditPayload,
        ("identity", "school_adapter", "room", "monitoring", "notification", "payment", "gateway"),
    ),
}
