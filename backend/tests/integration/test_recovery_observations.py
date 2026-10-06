"""真实两库：恢复计数缺失/倒退拒绝，所有缓存序号及跨批owner均被检查。"""

import asyncio
from uuid import UUID

import pytest
from query_resource_support import database, requires_mysql, seed_binding

from services.common.sql import execute
from services.deployment.recovery_observations import (
    ObservationWatermarkError,
    verify_observations,
)

pytestmark = requires_mysql


def test_restore_watermarks_fail_closed_across_batches():
    async def case():
        async with database("room") as room, database("school_adapter") as adapter:
            for index in range(1, 253):
                owner, binding = UUID(int=index), UUID(int=index + 1000)
                await seed_binding(room, owner, binding)
                async with room.begin() as conn:
                    await execute(conn, "INSERT INTO room_balance_cache "
                        "(binding_id,source,quality,observation_sequence,last_success_sequence,"
                        "last_error_sequence) VALUES (:id,'school_bound_rooms','stale',9,8,9)",
                        id=binding.bytes)
                async with adapter.begin() as conn:
                    await execute(conn, "INSERT INTO balance_observation_counters "
                        "(owner_user_id,sequence) VALUES (:id,9)", id=owner.bytes)
            assert await verify_observations(room, adapter) == 252
            async with adapter.begin() as conn:
                await execute(conn, "DELETE FROM balance_observation_counters "
                              "WHERE owner_user_id=:id", id=UUID(int=252).bytes)
            with pytest.raises(ObservationWatermarkError):
                await verify_observations(room, adapter)
            async with adapter.begin() as conn:
                await execute(conn, "INSERT INTO balance_observation_counters "
                              "(owner_user_id,sequence) VALUES (:id,8)", id=UUID(int=252).bytes)
            with pytest.raises(ObservationWatermarkError):
                await verify_observations(room, adapter)
            async with adapter.begin() as conn:
                await execute(conn, "UPDATE balance_observation_counters SET sequence=10")
            async with room.begin() as conn:
                await execute(conn, "UPDATE room_balance_cache SET observation_sequence=NULL,"
                              "last_success_sequence=11 WHERE binding_id=:id",
                              id=UUID(int=1252).bytes)
            with pytest.raises(ObservationWatermarkError):
                await verify_observations(room, adapter)
            async with room.begin() as conn:
                await execute(conn, "UPDATE room_balance_cache SET observation_sequence=NULL,"
                              "last_success_sequence=NULL,last_error_sequence=NULL")
            assert await verify_observations(room, adapter) == 252  # 旧缓存无排序证据。
    asyncio.run(case())
