"""支付同源入口，全部读写均重新 introspect 当前应用会话。"""

import base64
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import Response

from services.common.browser_security import require_browser_write
from services.common.dates import check_range
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.payment.dto import OrderCancelRequest, OrderRequest

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


@router.get("/room-bindings/{id}/payment-records")
async def records(id: UUID, request: Request, start_date: date, end_date: date):
    check_range(start_date, end_date)
    return success(request, await call(request, "records", {
        "binding_id": str(id), "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }))


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


@router.post("/payment-orders/{id}/cancel")
async def cancel_order(id: UUID, command: OrderCancelRequest, request: Request):
    return success(request, await call(
        request, "cancel", {"order_id": str(id), **command.model_dump(mode="json")}, write=True
    ))


@router.get("/payment-orders/{id}/qr")
async def qr(id: UUID, request: Request):
    value = await call(request, "qr", {"order_id": str(id)})
    if "image_base64" not in value:
        response = success(request, value, status=202)
        response.headers["Retry-After"] = str(value["retry_after_seconds"])
        return response
    try:
        if len(value["image_base64"]) > 2_800_000 or value["mime"] not in {
            "image/png",
            "image/jpeg",
        }:
            raise ValueError()
        raw = base64.b64decode(value["image_base64"], validate=True)
    except (ValueError, TypeError):
        raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "二维码图片格式异常") from None
    return Response(
        raw,
        media_type=value["mime"],
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/payment-orders/{id}/qr-refresh", status_code=202)
async def refresh_qr(
    id: UUID,
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=16, max_length=128)],
):
    return success(
        request,
        await call(
            request,
            "qr-refresh",
            {"order_id": str(id), "idempotency_key": idempotency_key},
            write=True,
        ),
        status=202,
    )
