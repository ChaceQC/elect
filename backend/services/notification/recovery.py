"""只有 DATA 前崩溃可安全重试；正文边界后未知且占名额。"""

from services.common.ids import new_id
from services.common.sql import execute

from .results import settle
from .smtp import DeliveryOutcome


async def recovery_tick(engine):
    async with engine.begin() as conn:
        rows = (
            (
                await execute(
                    conn,
                    "SELECT * FROM notification_jobs WHERE state='sending' "
                    "AND lease_until<=UTC_TIMESTAMP(6) ORDER BY lease_until,id "
                    "LIMIT 100 FOR UPDATE SKIP LOCKED",
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            await settle(
                conn,
                row,
                DeliveryOutcome(
                    "delivery_unknown" if row["body_started_at"] else "retry_wait",
                    "SMTP_WORKER_LOST_AFTER_DATA"
                    if row["body_started_at"]
                    else "SMTP_WORKER_LOST_BEFORE_DATA",
                ),
                new_id(),
                recovering=True,
            )
    return bool(rows)
