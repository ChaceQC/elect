"""仅合成样本的长期索引对照夹具。"""

from datetime import datetime, timedelta

from sqlalchemy import text

from services.common.ids import new_id
from services.common.sql import execute
from services.monitoring.repository import lock_monitor

RUN_SQL = ("INSERT INTO monitor_runs (id,monitor_id,generation,scheduled_for,binding_id,"
           "credential_version,state,version,attempt_count,execution_epoch) "
           "VALUES (:run,:monitor,1,:time,:binding,1,'succeeded',1,0,1)")
SAMPLE_SQL = ("INSERT INTO monitor_samples (id,run_id,monitor_id,owner_user_id,binding_id,"
              "captured_at,balance,quality,credential_version,meter_source_record_key) "
              "VALUES (:id,:run,:monitor,:owner,:binding,:time,25.50,'balance_only',1,:key)")


async def seed(engine, owner, binding, count, *, offset=0, monitor=None):
    async with engine.begin() as conn:
        monitor = monitor or (await lock_monitor(conn, owner))["id"]
        for start in range(offset, offset + count, 250):
            rows = [{"id": new_id().bytes, "run": new_id().bytes, "monitor": monitor,
                     "owner": owner.bytes, "binding": binding.bytes,
                     "time": datetime(2024, 6, 1) + timedelta(hours=i), "key": f"reading-{i}"}
                    for i in range(start, min(start + 250, offset + count))]
            await conn.execute(text(RUN_SQL), rows)
            await conn.execute(text(SAMPLE_SQL), rows)
    return monitor


async def handlers(conn):
    result = await execute(conn, "SHOW SESSION STATUS WHERE Variable_name IN "
                           "('Handler_read_key','Handler_read_next','Handler_read_rnd_next')")
    return {r[0]: int(r[1]) for r in result.all()}
