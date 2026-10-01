"""本人支付入口；浏览器不能指定学校标识、支付 URL 或状态。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import (
    BindingQuery,
    OperationQuery,
    OrderQuery,
    PaymentDispatchProof,
    PaymentProofQuery,
)
from services.common.security import Principal, require_user_principal
from services.common.sql import execute

from .dto import Capabilities, OrderRequest, QRPending
from .orders import accepted, create_order, get_order, order_view, reference, replay, unresolved
from .policy import MAXIMUM, MINIMUM, STEP, unavailable, validate_amount

router = APIRouter(prefix="/internal/v1")
Browser = Annotated[Principal, Depends(require_user_principal("payment:browser"))]


class CreateCommand(OrderRequest):
    idempotency_key: str = Field(min_length=16, max_length=128)


class QRCommand(OrderQuery):
    idempotency_key: str = Field(min_length=16, max_length=128)


async def context(state, principal, binding):
    room = await state.service_client.call(
        "room",
        "/browser/binding",
        "room:browser",
        principal.request_id,
        {"binding_id": str(binding)},
        principal=principal,
    )
    credential = await state.service_client.call(
        "school_adapter",
        "/credentials/control-view",
        "credential:control-read",
        principal.request_id,
        principal=principal,
    )
    return room, credential


@router.post("/browser/capabilities")
async def capabilities(command: BindingQuery, request: Request, principal: Browser):
    state = request.app.state
    room, credential = await context(state, principal, command.binding_id)
    pending = await unresolved(state.database, principal.user_id, command.binding_id)
    reason = unavailable(state.side_effect_policy, credential, room)
    return Capabilities(
        enabled=reason is None,
        currency="CNY",
        min_amount=str(MINIMUM),
        max_amount=str(MAXIMUM),
        amount_step=str(STEP),
        unavailable_reason=reason,
        unresolved_order=reference(pending) if pending else None,
    )


@router.post("/browser/create")
async def create(command: CreateCommand, request: Request, principal: Browser):
    state = request.app.state
    prior = await replay(state.database, principal.user_id, command)
    if prior:
        return accepted(prior)
    validate_amount(command.amount)
    room, credential = await context(state, principal, command.binding_id)
    reason = unavailable(state.side_effect_policy, credential, room)
    if reason:
        raise ApiError(403, ErrorCode.PAYMENT_UNAVAILABLE, reason)
    return await create_order(state.database, principal, command, room, credential)


@router.post("/browser/order")
async def read_order(command: OrderQuery, request: Request, principal: Browser):
    row = await get_order(request.app.state.database, principal.user_id, command.order_id)
    async with request.app.state.database.begin() as conn:
        await execute(
            conn,
            "UPDATE payment_orders SET next_check_at=UTC_TIMESTAMP(6) "
            "WHERE id=:id AND state IN ('awaiting_payment','status_unknown','submit_unknown') "
            "AND (last_checked_at IS NULL OR "
            "last_checked_at<=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 15 SECOND)) "
            "AND (check_lease_until IS NULL OR check_lease_until<=UTC_TIMESTAMP(6))",
            id=command.order_id.bytes,
        )
    return order_view(row)


@router.post("/browser/qr")
async def qr(command: OrderQuery, request: Request, principal: Browser):
    row = await get_order(request.app.state.database, principal.user_id, command.order_id)
    if row["state"] in {"paid_confirmed", "rejected", "expired_confirmed", "closed_confirmed"}:
        raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "订单已终结，请查询支付结果")
    if row["qr_status"] == "ready":
        value = await request.app.state.service_client.call(
            "school_adapter",
            "/payments/image",
            "school:payment",
            principal.request_id,
            command.model_dump(mode="json"),
            principal=principal,
        )
        if value["image_base64"]:
            return value
        raise ApiError(
            502, ErrorCode.SCHOOL_INVALID_RESPONSE, "二维码图片未取得，请重新获取原订单图片"
        )
    if row["qr_status"] == "failed":
        raise ApiError(
            502, ErrorCode.SCHOOL_INVALID_RESPONSE, "二维码获取失败，请重新获取原订单图片"
        )
    return QRPending(
        order_id=command.order_id,
        qr_status=row["qr_status"],
        poll_url=f"/api/v1/payment-orders/{command.order_id}/qr",
        retry_after_seconds=5,
    ).model_dump(mode="json")


@router.post("/browser/qr-refresh")
async def refresh_qr(command: QRCommand, request: Request, principal: Browser):
    from .qr import refresh

    return await refresh(
        request.app.state.database, principal.user_id, command.order_id, command.idempotency_key
    )


@router.post("/browser/operation")
async def read_operation(command: OperationQuery, request: Request, principal: Browser):
    from .qr import operation

    return await operation(request.app.state.database, principal.user_id, command.operation_id)


@router.post("/controls/dispatch-proof", response_model=PaymentDispatchProof)
async def dispatch_proof(
    command: PaymentProofQuery,
    request: Request,
    principal: Annotated[Principal, Depends(require_user_principal("payment:proof"))],
):
    from .jobs import dispatch_proof as proof

    return await proof(request.app.state.database, principal.user_id, command)
