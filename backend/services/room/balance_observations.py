"""唯一余额写入口；调用方须先持owner偏好锁，时间只展示、序号决定顺序。"""

import hashlib
import json
from datetime import UTC
from decimal import Decimal

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import BalanceReading
from services.common.logging import log
from services.common.sql import execute, first


async def apply_observation(conn, binding, amount, observation, error=None):
    if observation is None:
        return False  # 旧写者或未取得学校结果的错误不能破坏已排序缓存。
    reading = BalanceReading.model_validate(observation)
    failure = error or reading.error_code or (ErrorCode.SCHOOL_INVALID_RESPONSE
                                             if amount is None else None)
    amount = None if failure else format(Decimal(amount), ".2f")
    digest = hashlib.sha256(json.dumps(
        {**reading.model_dump(mode="json"), "amount": amount, "error": failure},
        sort_keys=True, separators=(",", ":"),
    ).encode()).digest()
    row = await first(conn, "SELECT * FROM room_balance_cache WHERE binding_id=:id FOR UPDATE",
                      id=binding)
    if row and row["observation_sequence"] is not None:
        if row["observation_sequence"] > reading.sequence:
            return False
        if row["observation_sequence"] == reading.sequence:
            if row["observation_hash"] != digest:
                log("balance_observation_conflict", service="room",
                    request_id=str(reading.request_id), error_code="VERSION_CONFLICT")
                raise ApiError(409, ErrorCode.VERSION_CONFLICT, "余额观测序号存在冲突")
            return True
    at = reading.observed_at.astimezone(UTC).replace(tzinfo=None)
    await execute(
        conn, "INSERT INTO room_balance_cache (binding_id,balance,fetched_at,source,quality,"
        "error_code,observation_sequence,observation_hash,last_success_sequence,"
        "last_error_sequence,last_error_at,last_error_code) VALUES "
        "(:id,:amount,IF(:error IS NULL,:at,NULL),:source,IF(:error IS NULL,'fresh','unknown'),"
        ":error,:seq,:hash,IF(:error IS NULL,:seq,NULL),IF(:error IS NULL,NULL,:seq),"
        "IF(:error IS NULL,NULL,:at),:error) ON DUPLICATE KEY UPDATE "
        "balance=IF(:error IS NULL,:amount,balance),fetched_at=IF(:error IS NULL,:at,fetched_at),"
        "source=:source,quality=IF(:error IS NULL,'fresh',IF(balance IS NULL,'unknown','stale')),"
        "error_code=:error,observation_sequence=:seq,observation_hash=:hash,"
        "last_success_sequence=IF(:error IS NULL,:seq,last_success_sequence),"
        "last_error_sequence=IF(:error IS NULL,last_error_sequence,:seq),"
        "last_error_at=IF(:error IS NULL,last_error_at,:at),"
        "last_error_code=IF(:error IS NULL,last_error_code,:error),updated_at=UTC_TIMESTAMP(6)",
        id=binding, amount=amount, at=at, source=reading.source, error=failure,
        seq=reading.sequence, hash=digest,
    )
    return True
