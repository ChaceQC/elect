"""Notification 发送前的唯一许可入口；取消与许可按同一 monitor 锁串行。"""

from datetime import timedelta
from uuid import UUID

from services.common.ids import new_id
from services.common.internal_dto import SendPermit
from services.common.sql import aware, execute, first

from .repository import lock_monitor


def denied(code):
    return SendPermit(permitted=False, permit_id=None, expires_at=None, denial_code=code)


async def authorize(engine, command):
    async with engine.begin() as conn:
        monitor = await lock_monitor(conn, command.owner_user_id)
        episode = await first(
            conn,
            "SELECT e.* FROM alert_episodes e JOIN alert_slots s ON s.episode_id=e.id "
            "WHERE s.id=:id AND e.monitor_id=:monitor FOR UPDATE",
            id=command.alert_slot_id.bytes,
            monitor=monitor["id"],
        )
        if not episode:
            return denied("SLOT_NOT_FOUND")
        slot = await first(
            conn,
            "SELECT * FROM alert_slots WHERE id=:id FOR UPDATE",
            id=command.alert_slot_id.bytes,
        )
        if (
            monitor["state"] != "active"
            or not monitor["desired_enabled"]
            or not monitor["credential_allowed"]
            or monitor["credential_operation_id"]
            or episode["state"] != "open"
            or episode["generation"] != monitor["generation"]
            or episode["id"] != monitor["current_episode_id"]
            or episode["binding_id"] != monitor["binding_id"]
            or command.generation != monitor["generation"]
            or slot["generation"] != command.generation
            or command.email_version != monitor["email_version"]
            or slot["email_version"] != command.email_version
            or slot["ordinal"] > monitor["repeat_limit"]
        ):
            return denied("AUTHORIZATION_CHANGED")
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
        now = clock["now"]
        previous = await first(
            conn,
            "SELECT * FROM send_permits WHERE job_id=:job AND execution_epoch=:epoch",
            job=command.job_id.bytes,
            epoch=command.execution_epoch,
        )
        if previous:
            if (
                previous["alert_slot_id"] != slot["id"]
                or slot["permit_id"] != previous["id"]
                or slot["state"] != "authorized"
                or previous["expires_at"] <= now
            ):
                return denied("PERMIT_EXPIRED_OR_CONFLICT")
            return SendPermit(
                permitted=True,
                permit_id=UUID(bytes=previous["id"]),
                expires_at=aware(previous["expires_at"]),
                denial_code=None,
            )
        if slot["state"] != "reserved":
            return denied("SLOT_NOT_RESERVED")
        if slot["delivery_id"] and slot["delivery_id"] != command.job_id.bytes:
            return denied("JOB_CONFLICT")
        sample = await first(
            conn,
            "SELECT s.*,r.generation AS run_generation FROM monitor_samples s "
            "JOIN monitor_runs r ON r.id=s.run_id WHERE s.id=:id",
            id=slot["sample_id"],
        )
        if (
            not sample
            or sample["monitor_id"] != monitor["id"]
            or sample["owner_user_id"] != monitor["owner_user_id"]
            or sample["run_generation"] != monitor["generation"]
            or sample["id"] != monitor["last_sample_id"]
            or sample["binding_id"] != monitor["binding_id"]
            or sample["credential_version"] != monitor["credential_version"]
            or sample["balance"] >= monitor["threshold"]
            or not now - timedelta(minutes=5) <= sample["captured_at"] <= now
        ):
            return denied("SAMPLE_NOT_CURRENT")
        last = await first(
            conn,
            "SELECT MAX(s.authorized_at) AS at,SUM(s.state='authorized') AS in_flight "
            "FROM alert_slots s "
            "JOIN alert_episodes e ON e.id=s.episode_id WHERE e.monitor_id=:id "
            "AND (s.delivery_id IS NULL OR s.delivery_id<>:job)",
            id=monitor["id"],
            job=command.job_id.bytes,
        )
        if last["in_flight"]:
            return denied("DELIVERY_IN_FLIGHT")
        recent = max(filter(None, [last["at"], monitor["last_email_sent_at"]]), default=None)
        if recent and recent + timedelta(minutes=monitor["interval_minutes"]) > now:
            return denied("COOLDOWN")
        permit, expires = new_id(), now + timedelta(seconds=30)
        await execute(
            conn,
            "INSERT INTO send_permits (id,alert_slot_id,job_id,execution_epoch,expires_at) "
            "VALUES (:id,:slot,:job,:epoch,:expires)",
            id=permit.bytes,
            slot=slot["id"],
            job=command.job_id.bytes,
            epoch=command.execution_epoch,
            expires=expires,
        )
        await execute(
            conn,
            "UPDATE alert_slots SET state='authorized',permit_id=:permit,"
            "delivery_id=:job,"
            "authorized_at=UTC_TIMESTAMP(6),send_lease_until=:expires,updated_at=UTC_TIMESTAMP(6) "
            "WHERE id=:id",
            permit=permit.bytes,
            expires=expires,
            id=slot["id"],
            job=command.job_id.bytes,
        )
        return SendPermit(
            permitted=True, permit_id=permit, expires_at=aware(expires), denial_code=None
        )
