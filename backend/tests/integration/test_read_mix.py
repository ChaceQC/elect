"""只运行一次固定50账号对照；合成响应不代表真实学校容量验收。"""

import asyncio
import json

from query_resource_support import database, requires_mysql
from read_mix_support import scenario

pytestmark = requires_mysql


def test_fifty_owner_mixed_reads_with_original_pools(monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")

    async def case():
        results = []
        for slots in (1, 2):
            async with database("room", production_pool=True) as room:
                async with database("payment", production_pool=True) as payment:
                    results.append(await scenario(room, payment, slots))
        old, new = results
        assert all(new["first_fast"][domain] < 2 for domain in ("room", "payment"))
        assert all(old["first_fast"][domain] > 10 for domain in ("room", "payment"))
        assert new["read_p95_ms"] < 1000 and new["peak_slots"] == {"room": 2, "payment": 2}
        print("R5 mixed " + json.dumps({"one_slot": old, "two_slots": new}))
    asyncio.run(case())
