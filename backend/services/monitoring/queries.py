from uuid import UUID

from services.common.sql import aware, first

from .dto import Monitor
from .repository import in_flight, lock_monitor
from .runs import run_view


class MonitorQueries:
    def __init__(self, engine, crypto):
        self.engine, self.crypto = engine, crypto

    def config(self, row):
        return {
            "enabled": bool(row["desired_enabled"]),
            "interval_minutes": row["interval_minutes"],
            "repeat_limit": row["repeat_limit"],
            "threshold": format(row["threshold"], ".2f"),
            "email": self.crypto.open(
                row["email_ciphertext"], UUID(bytes=row["owner_user_id"]), row["email_version"]
            ),
        }

    async def get(self, owner):
        async with self.engine.begin() as conn:
            row = await lock_monitor(conn, owner)
            return await self.view(conn, row)

    async def view(self, conn, row):
        current = await first(
            conn,
            "SELECT * FROM monitor_runs WHERE monitor_id=:id AND state IN "
            "('pending','running','retry_wait','cancel_requested') "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            id=row["id"],
        )
        last = await first(
            conn,
            "SELECT * FROM monitor_runs WHERE monitor_id=:id "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            id=row["id"],
        )
        count, mails = await in_flight(conn, row)
        invalid = await first(
            conn,
            "SELECT COUNT(*) AS n FROM monitor_runs WHERE monitor_id=:id "
            "AND state='cancel_requested' AND lease_until>UTC_TIMESTAMP(6)",
            id=row["id"],
        )
        invalid_mail = await first(
            conn,
            "SELECT COUNT(*) AS n FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
            "WHERE e.monitor_id=:id AND s.state='authorized' AND "
            "(s.generation<>:generation OR s.email_version<>:email_version OR :state<>'active')",
            id=row["id"],
            generation=row["generation"],
            email_version=row["email_version"],
            state=row["state"],
        )
        notification = await self.notification(conn, row, mails)
        return Monitor(
            id=UUID(bytes=row["id"]),
            binding_id=UUID(bytes=row["binding_id"]) if row["binding_id"] else None,
            config=self.config(row),
            state=row["state"],
            health=row["health"],
            version=row["version"],
            generation=row["generation"],
            current_run=await run_view(conn, current),
            last_run=await run_view(conn, last),
            next_run_at=aware(row["next_run_at"]),
            last_success_at=aware(row["last_success_at"]),
            last_error_code=row["last_error_code"],
            in_flight_count=count,
            cancel_pending=bool(invalid["n"] or invalid_mail["n"]),
            notification=notification,
        )

    @staticmethod
    async def notification(conn, row, mails):
        latest = await first(
            conn,
            "SELECT s.state FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
            "WHERE e.monitor_id=:id ORDER BY s.updated_at DESC,s.id DESC LIMIT 1",
            id=row["id"],
        )
        unknown = await first(
            conn,
            "SELECT COUNT(*) AS n FROM alert_slots s JOIN alert_episodes e ON e.id=s.episode_id "
            "WHERE e.monitor_id=:id AND s.state='delivery_unknown'",
            id=row["id"],
        )
        state = latest["state"] if latest else "idle"
        if mails:
            state = "authorized"
        elif unknown["n"]:
            state = "delivery_unknown"
        return {
            "state": {"reserved": "pending", "authorized": "sending", "failed": "email_failed"}.get(
                state, state
            ),
            "last_sent_at": aware(row["last_email_sent_at"]),
            "last_error_code": None,
            "next_retry_at": None,
            "in_flight_count": mails,
            "delivery_unknown_count": unknown["n"],
        }
