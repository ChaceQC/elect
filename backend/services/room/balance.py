"""余额缓存与按账号合并的持久刷新；不创建 monitor sample。"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.sql import aware, execute, first

from .dto import Balance
from .preference_store import lock_preference, locked_operation
from .query_jobs import accept_query, target


async def get_balance(engine, owner, binding):
    async with engine.connect() as conn:
        await target(conn, owner, binding)
        row = await first(
            conn, "SELECT * FROM room_balance_cache WHERE binding_id=:id", id=binding.bytes
        )
        pending = await first(
            conn,
            "SELECT id FROM room_operations WHERE owner_user_id=:owner "
            "AND type='balance_refresh' AND state IN ('accepted','running') LIMIT 1",
            owner=owner.bytes,
        )
    fetched = aware(row["fetched_at"]) if row else None
    return Balance(
        amount=format(row["balance"], ".2f") if row and row["balance"] is not None else None,
        currency="CNY",
        source=row["source"] if row else None,
        fetched_at=fetched,
        school_observed_at=aware(row["school_observed_at"]) if row else None,
        stale=not fetched
        or row["observation_sequence"] is None
        or row["quality"] != "fresh"
        or (datetime.now(UTC) - fetched).total_seconds() > 300,
        refresh_state="pending"
        if pending
        else "failed"
        if row and row["error_code"]
        else "ready"
        if fetched
        else "idle",
        error_code=row["error_code"] if row else None,
    )


async def accept_refresh(engine, owner, binding, key):
    digest = hashlib.sha256(f"balance:{binding}".encode()).digest()
    async with engine.begin() as conn:
        operation, created = await accept_query(
            conn, owner, binding, key, "balance_refresh", digest
        )
        if not created:
            return operation
        pending = await first(
            conn,
            "SELECT id FROM room_operations WHERE owner_user_id=:owner "
            "AND type='balance_refresh' AND state IN ('accepted','running') AND id<>:id "
            "ORDER BY created_at,id LIMIT 1",
            owner=owner.bytes,
            id=operation.bytes,
        )
        if pending:
            # 新键也持久指向同一个刷新，不增加上游请求。
            await execute(
                conn,
                "UPDATE room_operations SET "
                "saga_step='merged',upstream_operation_id=:prior WHERE id=:id",
                id=operation.bytes,
                prior=pending["id"],
            )
        else:
            recent = await first(
                conn,
                "SELECT id FROM room_operations WHERE owner_user_id=:owner "
                "AND type='balance_refresh' "
                "AND state IN ('succeeded','failed') AND "
                "updated_at>DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 30 SECOND) LIMIT 1",
                owner=owner.bytes,
            )
            if recent:
                raise ApiError(
                    429,
                    ErrorCode.RATE_LIMITED,
                    "余额刷新冷却中，请稍后重试",
                    True,
                    retry_after_seconds=30,
                )
        return operation


async def claim_refresh(engine):
    async with engine.begin() as conn:
        candidate = await first(
            conn,
            "SELECT owner_user_id FROM room_operations WHERE type='balance_refresh' "
            "AND state IN ('accepted','running') AND (lease_until IS NULL OR "
            "lease_until<=UTC_TIMESTAMP(6)) ORDER BY created_at LIMIT 1",
        )
        if not candidate:
            return None
        await lock_preference(conn, UUID(bytes=candidate["owner_user_id"]))
        row = await first(
            conn,
            "SELECT * FROM room_operations WHERE owner_user_id=:owner AND "
            "type='balance_refresh' AND state IN ('accepted','running') AND "
            "saga_step<>'merged' AND (lease_until IS NULL OR "
            "lease_until<=UTC_TIMESTAMP(6)) ORDER BY created_at,id LIMIT 1 FOR UPDATE",
            owner=candidate["owner_user_id"],
        )
        if not row:
            return None
        lease = str(new_id())
        await execute(
            conn,
            "UPDATE room_operations SET "
            "state='running',lease_owner=:lease,lease_until=DATE_ADD(UTC_TIMESTAMP(6),"
            "INTERVAL 45 SECOND) WHERE id=:id",
            id=row["id"],
            lease=lease,
        )
        return {**row, "lease_owner": lease}


async def finish_refresh(engine, row, records, error, observation=None):
    from .balance_store import finish_operations, update_balances

    async with engine.begin() as conn:
        if not await locked_operation(conn, row):
            return False
        await update_balances(conn, row["owner_user_id"], records, error, observation)
        await finish_operations(conn, row["id"], records, error)
    return True
