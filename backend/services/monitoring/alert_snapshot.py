"""仅 Notification 本人上下文可读取的投递快照，地址不经过 MQ。"""

from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import AlertSnapshot
from services.common.sql import aware, first

from .alerts import sample_is_current


async def snapshot(app, command, principal):
    async with app.state.database.connect() as conn:
        monitor = await first(
            conn, "SELECT * FROM monitors WHERE owner_user_id=:id", id=command.owner_user_id.bytes
        )
        slot = await first(
            conn,
            "SELECT s.*,e.binding_id,e.threshold,p.balance,p.captured_at "
            "FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
            "JOIN monitor_samples p ON p.id=s.sample_id "
            "WHERE s.id=:id AND e.monitor_id=:monitor",
            id=command.alert_slot_id.bytes,
            monitor=monitor["id"] if monitor else None,
        )
        if not slot:
            raise ApiError(404, ErrorCode.NOT_FOUND, "提醒不存在")
        sample = await first(
            conn,
            "SELECT s.*,r.generation AS run_generation FROM monitor_samples s "
            "JOIN monitor_runs r ON r.id=s.run_id WHERE s.id=:id",
            id=slot["sample_id"],
        )
        clock = await first(conn, "SELECT UTC_TIMESTAMP(6) AS now")
    eligible = (
        slot["state"] == "reserved"
        and slot["generation"] == monitor["generation"]
        and slot["email_version"] == monitor["email_version"]
        and monitor["last_sample_id"] == sample["id"]
        and sample["balance"] < monitor["threshold"]
        and sample_is_current(monitor, sample, clock["now"])
    )
    name = None
    email = None
    if eligible:
        email = app.state.email_crypto.open(
            monitor["email_ciphertext"], command.owner_user_id, slot["email_version"]
        )
        binding = await app.state.service_client.call(
            "room",
            "/controls/query-target",
            "room:query",
            command.request_id,
            {"binding_id": str(UUID(bytes=slot["binding_id"]))},
            principal=principal,
        )
        name = binding["display_name"]
    return AlertSnapshot(
        alert_slot_id=command.alert_slot_id,
        eligible=eligible and bool(email),
        state=slot["state"],
        generation=slot["generation"],
        email_version=slot["email_version"],
        delivery_version=slot["delivery_version"],
        email=email,
        binding_id=UUID(bytes=slot["binding_id"]),
        display_name=name,
        balance=format(slot["balance"], ".2f"),
        threshold=format(slot["threshold"], ".2f"),
        captured_at=aware(slot["captured_at"]),
    )
