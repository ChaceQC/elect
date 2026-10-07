"""隔离且停写后的跨库只读门禁；不跨域授权，也不自动重置观测计数。"""

from sqlalchemy.ext.asyncio import create_async_engine

from services.common.sql import execute


class ObservationWatermarkError(ValueError):
    """恢复的生产者计数不能覆盖已持久化的消费者高水位。"""


async def verify_observations(room, adapter):
    after, checked = b"", 0
    while True:
        async with room.connect() as conn:
            rows = (await execute(conn,
                "SELECT b.owner_user_id AS owner,MAX(GREATEST("
                "COALESCE(c.observation_sequence,0),COALESCE(c.last_success_sequence,0),"
                "COALESCE(c.last_error_sequence,0))) AS watermark "
                "FROM room_bindings b JOIN room_balance_cache c ON c.binding_id=b.id "
                "WHERE b.owner_user_id>:after GROUP BY b.owner_user_id "
                "ORDER BY b.owner_user_id LIMIT 250", after=after)).mappings().all()
        if not rows:
            return checked
        params = {f"o{i}": row["owner"] for i, row in enumerate(rows)}
        placeholders = ",".join(f":{key}" for key in params)
        async with adapter.connect() as conn:
            counters = dict((await execute(conn,
                "SELECT owner_user_id,sequence FROM balance_observation_counters "
                f"WHERE owner_user_id IN ({placeholders})", **params)).all())
        if any(row["watermark"] > counters.get(row["owner"], 0) for row in rows):
            raise ObservationWatermarkError("恢复观测水位不一致，保持隔离并核对同一备份集")
        checked += len(rows)
        after = rows[-1]["owner"]


async def verify_urls(urls):
    # 仅一次性运维作业持有两个单连接池；业务池及本域账号权限不变。
    engines = [create_async_engine(urls[domain], pool_size=1, max_overflow=0,
               hide_parameters=True, isolation_level="READ COMMITTED")
               for domain in ("room", "school_adapter")]
    try:
        return await verify_observations(*engines)
    finally:
        for engine in engines:
            await engine.dispose()
