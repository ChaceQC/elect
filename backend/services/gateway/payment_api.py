"""支付同源入口，全部读写均重新 introspect 当前应用会话。"""

import base64
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import Response

from services.common.browser_security import require_browser_write
from services.common.errors import ErrorCode
from services.common.http import ApiError
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
