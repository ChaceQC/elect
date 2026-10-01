"""Notification 本域 job、唯一领取与执行栅栏。"""

from datetime import UTC

from services.common.ids import new_id
from services.common.sql import execute, first

from .template import TEMPLATE_VERSION


async def create_job(conn, event, snapshot, crypto, domain):
    if not snapshot.eligible:
        return
    payload = event.payload
    if payload.generation != snapshot.generation or payload.email_version != snapshot.email_version:
        return
    job = new_id()
    await execute(
        conn,
        "INSERT INTO notification_jobs (id,alert_slot_id,owner_user_id,email_ciphertext,generation,"
        "email_version,template_version,message_id,state,version,attempt_count,next_attempt_at,"
        "execution_epoch,binding_display_name,balance,threshold,captured_at) VALUES (:id,:slot,"
        ":owner,:email,:generation,:ev,:template,:message,'pending',1,0,UTC_TIMESTAMP(6),1,"
        ":name,:balance,:threshold,:at) ON DUPLICATE KEY UPDATE id=id",
        id=job.bytes,
        slot=payload.alert_slot_id.bytes,
        owner=payload.owner_user_id.bytes,
        email=crypto.seal(snapshot.email, payload.owner_user_id, payload.email_version),
        generation=payload.generation,
        ev=payload.email_version,
        template=TEMPLATE_VERSION,
        message=f"<elect-{payload.alert_slot_id}@{domain}>",
        name=snapshot.display_name,
        balance=snapshot.balance,
        threshold=snapshot.threshold,
        at=snapshot.captured_at.astimezone(UTC).replace(tzinfo=None),
    )


async def claim(engine, job_id=None):
    owner = str(new_id())
    async with engine.begin() as conn:
        row = await first(
            conn,
            "SELECT * FROM notification_jobs WHERE state IN ('pending','retry_wait') "
            "AND next_attempt_at<=UTC_TIMESTAMP(6) AND (:id IS NULL OR id=:id) "
            "ORDER BY next_attempt_at,id LIMIT 1 FOR UPDATE SKIP LOCKED",
            id=job_id.bytes if job_id else None,
        )
        if not row:
            return None
        await execute(
            conn,
            "UPDATE notification_jobs SET state='sending',version=version+1,"
            "execution_epoch=execution_epoch+1,lease_owner=:owner,lease_until=DATE_ADD("
            "UTC_TIMESTAMP(6),INTERVAL 45 SECOND),body_started_at=NULL WHERE id=:id",
            id=row["id"],
            owner=owner,
        )
        return dict(await first(conn, "SELECT * FROM notification_jobs WHERE id=:id", id=row["id"]))


async def locked_execution(conn, job):
    row = await first(
        conn,
        "SELECT *,UTC_TIMESTAMP(6) AS now FROM notification_jobs WHERE id=:id FOR UPDATE",
        id=job["id"],
    )
    if (
        not row
        or row["state"] != "sending"
        or row["lease_owner"] != job["lease_owner"]
        or row["execution_epoch"] != job["execution_epoch"]
        or row["lease_until"] <= row["now"]
    ):
        return None
    return row


async def record_permit(engine, job, permit):
    async with engine.begin() as conn:
        row = await locked_execution(conn, job)
        if not row or permit.expires_at.astimezone(UTC).replace(tzinfo=None) <= row["now"]:
            return False
        await execute(
            conn,
            "UPDATE notification_jobs SET permit_id=:permit,permit_expires_at=:at,"
            "attempt_count=attempt_count+1 WHERE id=:id",
            id=row["id"],
            permit=permit.permit_id.bytes,
            at=permit.expires_at.astimezone(UTC).replace(tzinfo=None),
        )
        job.update(permit_id=permit.permit_id.bytes, attempt_count=row["attempt_count"] + 1)
        await execute(
            conn,
            "INSERT INTO notification_attempts (id,job_id,attempt_no,state,started_at) "
            "VALUES (:id,:job,:attempt,'started',UTC_TIMESTAMP(6))",
            id=new_id().bytes,
            job=row["id"],
            attempt=job["attempt_count"],
        )
    return True


async def mark_body(engine, job):
    from .smtp import BodyDenied

    async with engine.begin() as conn:
        row = await locked_execution(conn, job)
        if (
            not row
            or not row["permit_id"]
            or row["permit_id"] != job["permit_id"]
            or row["permit_expires_at"] <= row["now"]
        ):
            raise BodyDenied()
        await execute(
            conn,
            "UPDATE notification_jobs SET body_started_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=row["id"],
        )


async def defer(engine, job):
    # 上一次回报尚未被 Monitoring 镜像，禁止先申请新许可盖过旧回报。
    async with engine.begin() as conn:
        if not await locked_execution(conn, job):
            return False
        await execute(
            conn,
            "UPDATE notification_jobs SET state='retry_wait',lease_owner=NULL,lease_until=NULL,"
            "next_attempt_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 15 SECOND) WHERE id=:id",
            id=job["id"],
        )
    return True
