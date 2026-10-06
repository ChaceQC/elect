"""只在显式运维采样时读容量估计，不按秒全表COUNT。"""

import json
import time

from services.common.sql import first


async def sample(engine, limit_mib, baseline=None, *, domain):
    if limit_mib is None or limit_mib < 1:
        raise ValueError("容量采样需要显式领域容量预算")
    async with engine.connect() as conn:
        row = await first(conn, "SELECT COALESCE(SUM(data_length+index_length),0) AS bytes,"
            "COALESCE(SUM(table_rows),0) AS rows_estimate FROM information_schema.tables "
            "WHERE table_schema=DATABASE()")
    size, now = int(row["bytes"]), int(time.time())
    result = {"allocated_bytes_estimate": size, "rows_estimate": int(row["rows_estimate"]),
              "sample_epoch": now, "capacity_limit_bytes": limit_mib * 1024 * 1024,
              "over_budget": int(size >= limit_mib * 1024 * 1024)}
    if baseline:
        document = json.loads(baseline.read_text(encoding="utf-8"))
        if document["domain"] != domain or document["kind"] != "capacity":
            raise ValueError("容量基线目标不匹配")
        previous = document["counts"]
        elapsed = now - previous["sample_epoch"]
        if elapsed > 0:
            result["growth_bytes_per_day"] = round(
                (size - previous["allocated_bytes_estimate"]) * 86400 / elapsed)
    return result
