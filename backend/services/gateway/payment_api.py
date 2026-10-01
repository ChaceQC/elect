"""支付同源入口，全部读写均重新 introspect 当前应用会话。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from services.common.browser_security import require_browser_write
from services.payment.dto import OrderRequest

from .api import session, success

router = APIRouter(prefix="/api/v1")


async def call(request, path, payload, *, write=False):
    principal, csrf = await session(request)
    if write:
        require_browser_write(request, csrf)
    return await request.app.state.service_client.call(
        "payment",
        "/browser/" + path,
        "payment:browser",
        principal.request_id,
        payload,
        principal=principal,
    )


@router.get("/payments/capabilities")
async def capabilities(request: Request, binding_id: UUID):
    return success(request, await call(request, "capabilities", {"binding_id": str(binding_id)}))


@router.post("/payment-orders", status_code=202)
async def create(
    command: OrderRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=16, max_length=128)],
):
    value = await call(
        request,
        "create",
        {**command.model_dump(mode="json"), "idempotency_key": idempotency_key},
        write=True,
    )
    return success(request, value, status=202)


@router.get("/payment-orders/{id}")
async def order(id: UUID, request: Request):
    return success(request, await call(request, "order", {"order_id": str(id)}))
