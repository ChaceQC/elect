"""在账号串行边界内归一化B02并以短事务分配观测序号。"""

from services.common.internal_dto import BalanceReading
from services.common.sql import execute, first

from .rooms import bound_rooms


async def observe(engine, owner, request_id, value, error, observed_at):
    from services.common.http import ApiError

    items = []
    if error is None:
        try:
            items = bound_rooms(value)
        except ApiError as failure:
            error = failure.code
    async with engine.begin() as conn:
        await execute(
            conn, "INSERT INTO balance_observation_counters (owner_user_id,sequence) "
            "VALUES (:owner,1) ON DUPLICATE KEY UPDATE sequence=sequence+1", owner=owner.bytes,
        )
        row = await first(conn, "SELECT sequence FROM balance_observation_counters "
                          "WHERE owner_user_id=:owner", owner=owner.bytes)
    observation = BalanceReading(sequence=row["sequence"], observed_at=observed_at,
                                 request_id=request_id, error_code=error)
    return {"items": items, "observation": observation.model_dump(mode="json")}
