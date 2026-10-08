"""订单自动处理期限；暂停与学校终态分开，期限不随读取或重试续期。"""

from datetime import UTC, datetime, timedelta

from services.common.sql import aware

from .states import ORDER

WINDOW_SECONDS = 15 * 60


def deadline_sql(prefix=""):
    return (f"COALESCE({prefix}check_deadline_at,"
            f"DATE_ADD({prefix}created_at,INTERVAL {WINDOW_SECONDS} SECOND))")


def deadline(row):
    return (aware(row.get("check_deadline_at"))
            or aware(row["created_at"]) + timedelta(seconds=WINDOW_SECONDS))


def observed_at(row):
    return aware(row.get("observed_at") or row.get("claimed_at")) or datetime.now(UTC)


def expired(row):
    return row["state"] not in ORDER.terminal and deadline(row) <= observed_at(row)


def in_flight(row):
    lease = aware(row.get("check_lease_until"))
    return bool(row.get("operation_in_flight") or lease and lease > observed_at(row))


def paused(row):
    return bool(not row["cancel_requested_at"] and expired(row) and not in_flight(row))
