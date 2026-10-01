"""新鲜成功样本的 episode/slot；调用者必须持有 monitor 锁。"""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from services.common.events import AlertReservedPayload
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.outbox import append_event
from services.common.sql import aware, execute, first

HYSTERESIS = Decimal("1.00")


def sample_is_current(monitor, sample, now):
    return bool(
        sample
        and monitor["desired_enabled"]
        and monitor["state"] == "active"
        and monitor["credential_allowed"]
        and not monitor["credential_operation_id"]
        and sample["monitor_id"] == monitor["id"]
        and sample["owner_user_id"] == monitor["owner_user_id"]
        and sample["binding_id"] == monitor["binding_id"]
        and sample["credential_version"] == monitor["credential_version"]
        and sample["run_generation"] == monitor["generation"]
        and sample["balance"] is not None
        and now - timedelta(minutes=5) <= sample["captured_at"] <= now
    )


async def refresh_counts(conn, monitor_id):
    await execute(
        conn,
        "UPDATE alert_episodes e SET sent_count=(SELECT COUNT(*) FROM alert_slots s "
        "WHERE s.episode_id=e.id AND s.state='sent'),reserved_count=(SELECT COUNT(*) "
        "FROM alert_slots s WHERE s.episode_id=e.id AND s.state IN ('reserved','authorized')) "
        "WHERE e.monitor_id=:id",
        id=monitor_id,
    )


async def wake_alert(conn, monitor, slot, request_id):
    clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
    await append_event(
        conn,
        EventEnvelope(
            event_id=new_id(),
            type="monitor.alert_reserved",
            schema_version=1,
            producer="monitoring",
            aggregate_id=UUID(bytes=monitor["id"]),
            aggregate_version=monitor["version"],
            occurred_at=aware(clock["now"]),
            request_id=request_id,
            payload=AlertReservedPayload(
                alert_slot_id=UUID(bytes=slot["id"]),
                owner_user_id=UUID(bytes=monitor["owner_user_id"]),
                generation=slot["generation"],
                email_version=slot["email_version"],
            ),
            dedupe_key=str(UUID(bytes=slot["id"])),
        ),
    )
    await execute(
        conn, "UPDATE alert_slots SET wake_at=UTC_TIMESTAMP(6) WHERE id=:id", id=slot["id"]
    )


async def cooldown(conn, monitor, now):
    last = await first(
        conn,
        "SELECT MAX(s.authorized_at) AS at,SUM(s.state='authorized') AS in_flight "
        "FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id WHERE e.monitor_id=:id",
        id=monitor["id"],
    )
    recent = max(filter(None, [last["at"], monitor["last_email_sent_at"]]), default=None)
    return bool(
        last["in_flight"]
        or recent
        and recent + timedelta(minutes=monitor["interval_minutes"]) > now
    )


async def on_sample(conn, monitor, sample_id, request_id):
    sample = await first(
        conn,
        "SELECT s.*,r.generation AS run_generation FROM monitor_samples s "
        "JOIN monitor_runs r ON r.id=s.run_id WHERE s.id=:id",
        id=sample_id.bytes,
    )
    clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
    if not sample_is_current(monitor, sample, clock["now"]):
        return None
    prior = await first(conn, "SELECT id FROM alert_slots WHERE sample_id=:id", id=sample_id.bytes)
    if prior:
        return None
    # 新样本使旧未授权快照失效；已取得许可的邮件保留在途事实。
    await execute(
        conn,
        "UPDATE alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
        "SET s.state='cancelled',s.finished_at=UTC_TIMESTAMP(6),s.next_retry_at=NULL,"
        "s.updated_at=UTC_TIMESTAMP(6) WHERE e.monitor_id=:id AND s.state='reserved'",
        id=monitor["id"],
    )
    episode = await first(
        conn,
        "SELECT * FROM alert_episodes WHERE monitor_id=:id AND state='open' FOR UPDATE",
        id=monitor["id"],
    )
    if episode and sample["balance"] >= episode["recovery_threshold"]:
        await execute(
            conn,
            "UPDATE alert_episodes SET state='closed',closed_at=UTC_TIMESTAMP(6) WHERE id=:id",
            id=episode["id"],
        )
        await execute(
            conn, "UPDATE monitors SET current_episode_id=NULL WHERE id=:id", id=monitor["id"]
        )
    elif sample["balance"] < monitor["threshold"]:
        if not episode:
            episode = await open_episode(conn, monitor)
        await reserve(conn, monitor, episode, sample, clock["now"], request_id)
    await refresh_counts(conn, monitor["id"])


async def open_episode(conn, monitor):
    episode_id = new_id()
    await execute(
        conn,
        "INSERT INTO alert_episodes (id,monitor_id,binding_id,generation,opened_at,state,"
        "threshold,recovery_threshold,sent_count,reserved_count) VALUES (:id,:monitor,:binding,"
        ":generation,UTC_TIMESTAMP(6),'open',:threshold,:recovery,0,0)",
        id=episode_id.bytes,
        monitor=monitor["id"],
        binding=monitor["binding_id"],
        generation=monitor["generation"],
        threshold=monitor["threshold"],
        recovery=monitor["threshold"] + HYSTERESIS,
    )
    await execute(
        conn,
        "UPDATE monitors SET current_episode_id=:episode WHERE id=:id",
        id=monitor["id"],
        episode=episode_id.bytes,
    )
    return await first(conn, "SELECT * FROM alert_episodes WHERE id=:id", id=episode_id.bytes)


async def reserve(conn, monitor, episode, sample, now, request_id):
    slots = (
        (await execute(conn, "SELECT * FROM alert_slots WHERE episode_id=:id", id=episode["id"]))
        .mappings()
        .all()
    )
    if any(slot["state"] == "failed" for slot in slots) or await cooldown(conn, monitor, now):
        return None
    occupied = {s["ordinal"] for s in slots if s["state"] != "cancelled"}
    if len(occupied) >= monitor["repeat_limit"]:
        return None
    ordinal = next((n for n in range(1, monitor["repeat_limit"] + 1) if n not in occupied), None)
    if ordinal is None:
        return None
    slot_id = new_id()
    await execute(
        conn,
        "INSERT INTO alert_slots (id,episode_id,ordinal,sample_id,generation,email_version,"
        "state) VALUES (:id,:episode,:ordinal,:sample,:generation,:email_version,'reserved')",
        id=slot_id.bytes,
        episode=episode["id"],
        ordinal=ordinal,
        sample=sample["id"],
        generation=monitor["generation"],
        email_version=monitor["email_version"],
    )
    slot = await first(conn, "SELECT * FROM alert_slots WHERE id=:id", id=slot_id.bytes)
    await wake_alert(conn, monitor, slot, request_id)
    return slot_id
