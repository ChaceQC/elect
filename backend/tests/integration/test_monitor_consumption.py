"""真实MySQL日聚合，使用随机空库与合成样本，不触及业务环境。"""

import asyncio
from datetime import UTC, date, datetime

from query_resource_support import database, requires_mysql
from sample_lookup_support import RUN_SQL, SAMPLE_SQL

from services.common.ids import new_id
from services.common.internal_dto import HistoryWindowQuery
from services.common.sql import execute
from services.monitoring.consumption import daily_estimates

pytestmark = requires_mysql


async def insert(conn, owner, binding, time, balance, previous=None):
    from services.monitoring.repository import lock_monitor

    monitor = (await lock_monitor(conn, owner))["id"]
    sample, run = new_id().bytes, new_id().bytes
    await execute(conn, RUN_SQL, run=run, monitor=monitor,
                  time=datetime.now(UTC).replace(tzinfo=None), binding=binding.bytes)
    await execute(conn, SAMPLE_SQL, id=sample, run=run, monitor=monitor, owner=owner.bytes,
                  binding=binding.bytes, time=datetime.fromisoformat(time), key=None)
    await execute(conn, "UPDATE monitor_samples SET balance=:balance,previous_sample_id=:previous "
                  "WHERE id=:id", balance=balance, previous=previous, id=sample)
    return sample


def test_balance_estimates_keep_external_baseline_and_isolate_owner_binding_and_day():
    async def case():
        async with database("monitoring") as engine:
            owner, other_owner, binding, other_binding = (new_id() for _ in range(4))
            async with engine.begin() as conn:
                # 上海9月30日23:59的基线在请求日期之外，10月1日午夜仍可计算。
                previous = await insert(conn, owner, binding, "2026-09-30T15:59:00", "100.00")
                for time, balance in [("16:00:00", "98.80"), ("17:00:00", "108.80"),
                                      ("18:00:00", "108.80"), ("19:00:00", "108.70")]:
                    previous = await insert(conn, owner, binding, f"2026-09-30T{time}",
                                            balance, previous)
                foreign = await insert(conn, other_owner, binding, "2026-09-30T19:00:00", "500")
                other = await insert(conn, owner, other_binding, "2026-09-30T19:00:00", "600")
                await insert(conn, owner, binding, "2026-09-30T20:00:00", "1", foreign)
                await insert(conn, owner, binding, "2026-09-30T21:00:00", "1", other)
                await insert(conn, owner, binding, "2026-10-01T16:00:00", "100.00", previous)
            command = HistoryWindowQuery(binding_id=binding, start_date=date(2026, 10, 1),
                                         end_date=date(2026, 10, 1))
            result = await daily_estimates(engine, owner, command)
            assert result == {"days": [{"record_date": "2026-10-01", "amount": "1.30"}],
                              "sample_count": 6}
            assert (await daily_estimates(engine, new_id(), command))["days"] == []
            other_result = await daily_estimates(engine, other_owner, command)
            assert other_result["days"][0]["amount"] is None
    asyncio.run(case())


def test_first_topup_zero_and_same_time_baseline_are_distinct():
    async def case():
        async with database("monitoring") as engine:
            owner, binding = new_id(), new_id()
            async with engine.begin() as conn:
                previous = await insert(conn, owner, binding, "2026-09-28T00:00:00", "10.00")
                previous = await insert(conn, owner, binding, "2026-09-29T00:00:00", "20", previous)
                previous = await insert(conn, owner, binding, "2026-09-30T00:00:00", "20", previous)
                await insert(conn, owner, binding, "2026-09-30T00:00:00", "1", previous)
            result = await daily_estimates(engine, owner, HistoryWindowQuery(
                binding_id=binding, start_date=date(2026, 9, 28), end_date=date(2026, 9, 30)))
            assert [r["amount"] for r in result["days"]] == [None, None, "0.00"]
    asyncio.run(case())
