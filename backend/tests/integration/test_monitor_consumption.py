"""真实MySQL日聚合，使用随机空库与合成样本，不触及业务环境。"""

import asyncio
from datetime import UTC, date, datetime

from query_resource_support import database, requires_mysql
from sample_lookup_support import RUN_SQL, SAMPLE_SQL

from services.common.ids import new_id
from services.common.internal_dto import HistoryWindowQuery
from services.common.sql import execute
from services.gateway.consumption import merge_consumption
from services.monitoring.consumption import daily_estimates
from services.room.consumption import aggregate
from services.room.dto import Consumption

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
                # 10月1日首次减少归9月30日，10月2日首次减少补入10月1日。
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
            assert result == {"days": [{"record_date": "2026-10-01", "amount": "8.80"}],
                              "sample_count": 6}
            previous_day = await daily_estimates(engine, owner, HistoryWindowQuery(
                binding_id=binding, start_date=date(2026, 9, 30), end_date=date(2026, 9, 30)))
            assert previous_day["days"] == [{"record_date": "2026-09-30", "amount": "1.20"}]
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


def test_first_decrease_after_zero_and_topup_is_stable_across_date_filters():
    async def case():
        async with database("monitoring") as engine:
            owner, binding = new_id(), new_id()
            async with engine.begin() as conn:
                previous = await insert(conn, owner, binding, "2026-09-30T00:00:00", "100")
                for time, balance in [("00:00:00", "100"), ("01:00:00", "110"),
                                      ("02:00:00", "109.50"), ("03:00:00", "109.25")]:
                    previous = await insert(conn, owner, binding, f"2026-10-01T{time}",
                                            balance, previous)
            start, end = date(2026, 9, 30), date(2026, 10, 1)
            together = await daily_estimates(engine, owner, HistoryWindowQuery(
                binding_id=binding, start_date=start, end_date=end))
            assert together["days"] == [{"record_date": "2026-09-30", "amount": "0.50"},
                                        {"record_date": "2026-10-01", "amount": "0.25"}]
            for day, expected in zip((start, end), together["days"], strict=True):
                separate = await daily_estimates(engine, owner, HistoryWindowQuery(
                    binding_id=binding, start_date=day, end_date=day))
                assert separate["days"] == [expected]
    asyncio.run(case())


def test_attributed_day_drives_school_precedence_and_week_month_totals():
    async def case():
        async with database("monitoring") as engine:
            owner, binding = new_id(), new_id()
            async with engine.begin() as conn:
                previous = await insert(conn, owner, binding, "2026-09-25T15:00:00", "20")
                for time, balance in [("2026-09-28T01:00:00", "17"),
                                      ("2026-09-28T02:00:00", "16"),
                                      ("2026-09-30T14:00:00", "16"),
                                      ("2026-10-01T01:00:00", "14"),
                                      ("2026-10-01T02:00:00", "13")]:
                    previous = await insert(conn, owner, binding, time, balance, previous)
            start, end = date(2026, 9, 27), date(2026, 10, 1)
            estimates = await daily_estimates(engine, owner, HistoryWindowQuery(
                binding_id=binding, start_date=start, end_date=end))
            # 多日间隔只归前一自然日；学校9月30日金额优先覆盖已归回的估算。
            buckets, summary = aggregate([
                {"record_date": date(2026, 9, 30), "charged_amount": "5.00", "energy_usage": None}
            ], start, end, "day")
            history = Consumption(binding_id=binding, start_date=start, end_date=end,
                                  granularity="day", buckets=buckets, summary=summary,
                                  coverage="partial", sync_status="partial", sync_operation=None,
                                  version=1).model_dump(mode="json")
            assert estimates["days"][0] == {"record_date": "2026-09-27", "amount": "3.00"}
            weekly = merge_consumption(history, estimates, "week")
            monthly = merge_consumption(history, estimates, "month")
            assert [b["amount"] for b in weekly["buckets"]] == ["3.00", "7.00"]
            assert [b["amount"] for b in monthly["buckets"]] == ["9.00", "1.00"]
            assert monthly["summary"]["estimated_amount"] == "5.00"
    asyncio.run(case())
