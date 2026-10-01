"""持久投递领取、当前许可与 SMTP；不在 SQL 行锁中等待服务或网络。"""

import asyncio
from uuid import UUID

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import AlertSnapshot, SendPermit
from services.common.security import Principal

from .repository import claim, defer, mark_body, record_permit
from .results import finish
from .smtp import DeliveryOutcome
from .template import render


def principal(job, request_id):
    return Principal("notification", UUID(bytes=job["owner_user_id"]), 1, request_id)


async def get_snapshot(app, payload, request_id):
    owner = payload.owner_user_id
    async with asyncio.timeout(10):
        value = await app.state.service_client.call(
            "monitoring",
            "/alert-slots/snapshot",
            "monitor:alert-read",
            request_id,
            {
                "owner_user_id": str(owner),
                "request_id": str(request_id),
                "alert_slot_id": str(payload.alert_slot_id),
            },
            principal=Principal("notification", owner, 1, request_id),
        )
    return AlertSnapshot.model_validate(value)


async def execute_job(app, job):
    request_id = new_id()
    from services.common.events import AlertReservedPayload

    payload = AlertReservedPayload(
        alert_slot_id=UUID(bytes=job["alert_slot_id"]),
        owner_user_id=UUID(bytes=job["owner_user_id"]),
        generation=job["generation"],
        email_version=job["email_version"],
    )
    try:
        snapshot = await get_snapshot(app, payload, request_id)
        if snapshot.delivery_version < job["reported_version"]:
            return await defer(app.state.database, job)
        if not snapshot.eligible:
            return await finish(
                app.state.database,
                job,
                DeliveryOutcome("cancelled", "ALERT_NO_LONGER_CURRENT"),
                request_id,
            )
        async with asyncio.timeout(10):
            value = await app.state.service_client.call(
                "monitoring",
                "/alert-slots/authorize-send",
                "monitor:authorize-send",
                request_id,
                {
                    **payload.model_dump(mode="json"),
                    "job_id": str(UUID(bytes=job["id"])),
                    "request_id": str(request_id),
                    "execution_epoch": job["execution_epoch"],
                },
                principal=principal(job, request_id),
            )
        permit = SendPermit.model_validate(value)
    except (ApiError, TimeoutError):
        return await finish(
            app.state.database,
            job,
            DeliveryOutcome("retry_wait", "MONITORING_UNAVAILABLE"),
            request_id,
        )
    if not permit.permitted:
        waiting = permit.denial_code in {"DELIVERY_IN_FLIGHT", "COOLDOWN", "SLOT_NOT_RESERVED"}
        return await finish(
            app.state.database,
            job,
            DeliveryOutcome("retry_wait" if waiting else "cancelled", permit.denial_code),
            request_id,
        )
    if not await record_permit(app.state.database, job, permit):
        return await finish(
            app.state.database, job, DeliveryOutcome("cancelled", "SEND_PERMIT_EXPIRED"), request_id
        )
    recipient = app.state.email_crypto.open(
        job["email_ciphertext"], UUID(bytes=job["owner_user_id"]), job["email_version"]
    )
    message = render(job, app.state.smtp.config.sender, recipient, app.state.public_origin)
    outcome = await app.state.smtp.send(
        recipient, message, lambda: mark_body(app.state.database, job)
    )
    return await finish(app.state.database, job, outcome, request_id)


async def worker_tick(app, job_id=None):
    if app.state.smtp is None:
        # 仍检查 MySQL，默认禁外发不能绕过恢复和事件落库。
        from services.common.sql import execute

        async with app.state.database.connect() as conn:
            await execute(conn, "SELECT 1")
        return False
    job = await claim(app.state.database, job_id)
    return await execute_job(app, job) if job else False
