"""仅 Payment 身份可推进订单/表单，图片读取也校验本人订单归属。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.common.internal_dto import (
    DispatchOrder,
    OrderQuery,
    PaymentImage,
    PaymentSessionCommand,
    SchoolOrderResult,
    SchoolQRResult,
)
from services.common.security import Principal, authorize_owner, require_user_principal
from services.payment.records_dto import PaymentRecords, PaymentRecordsQuery

from .application.payment_flow import PaymentFlow
from .application.payment_orders import SchoolOrders
from .infrastructure.payment_sessions import PaymentSessions

router = APIRouter(prefix="/internal/v1/payments")
Payment = Annotated[Principal, Depends(require_user_principal("school:payment"))]


@router.post("/records", response_model=PaymentRecords)
async def records(command: PaymentRecordsQuery, request: Request, principal: Payment):
    from .application.payment_history import read

    return await read(request.app.state, principal, command)


@router.post("/dispatch", response_model=SchoolOrderResult)
async def dispatch(command: DispatchOrder, request: Request, principal: Payment):
    authorize_owner(principal, command.owner_user_id)
    return await SchoolOrders(request.app.state).dispatch(command, principal)


@router.post("/flow", response_model=SchoolQRResult)
async def flow(command: PaymentSessionCommand, request: Request, principal: Payment):
    authorize_owner(principal, command.owner_user_id)
    return await PaymentFlow(request.app.state).run(command, principal)


@router.post("/check", response_model=SchoolOrderResult)
async def check(command: OrderQuery, request: Request, principal: Payment):
    return await SchoolOrders(request.app.state).check(
        principal.user_id, command.order_id, principal.request_id
    )


@router.post("/image", response_model=PaymentImage)
async def image(command: OrderQuery, request: Request, principal: Payment):
    return await PaymentSessions(request.app.state).image(principal.user_id, command.order_id) or {
        "image_base64": None,
        "mime": None,
    }
