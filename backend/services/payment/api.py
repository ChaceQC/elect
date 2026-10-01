"""本人支付入口；浏览器不能指定学校标识、支付 URL 或状态。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import BindingQuery, OrderQuery
from services.common.security import Principal, require_user_principal

from .dto import Capabilities, OrderRequest
from .orders import accepted, create_order, get_order, order_view, reference, replay, unresolved
from .policy import MAXIMUM, MINIMUM, STEP, unavailable, validate_amount

router = APIRouter(prefix="/internal/v1")
Browser = Annotated[Principal, Depends(require_user_principal("payment:browser"))]


class CreateCommand(OrderRequest):
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
    return order_view(
        await get_order(request.app.state.database, principal.user_id, command.order_id)
    )
