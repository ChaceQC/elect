"""T4 实际 MySQL/Redis + 合成学校：逐房间余额、窗口与历史修订。"""

import asyncio
import os
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import httpx

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from services.common.ids import new_id
from services.common.security import Principal
from services.common.sql import execute, first
from services.room.balance import accept_refresh, claim_refresh, finish_refresh
from services.room.dto import HistoryRequest
from services.room.history_jobs import accept_history, claim_history
from services.room.history_store import finish_history
from services.room.mirror import confirm_binding
from services.room.query_worker import query_tick
from services.room.worker import control_tick, sync_tick
from services.school_adapter.infrastructure.balance_observations import observe


class QuerySchool:
    def __init__(self, school):
        self.school = school
        self.bound_reads, self.history_reads = 0, 0
        self.missing_second, self.empty_history = False, False
        self.amount = "1.50"
        self.first_balance = "25.50"

    def handler(self, request):
        if request.url.path.endswith("queryRecordByTime"):
            self.history_reads += 1
            assert request.method == "GET"
            start = request.url.params["startTimeStr"]
            end = request.url.params["endTimeStr"]
            assert len(start) == len(end) == 8 and "buildId" in request.url.params
            day = date(int(start[:4]), int(start[4:6]), int(start[6:]))
            row = {
                "time": day.isoformat(),
                "trueAmount": self.amount,
                "energyUsage": "2.50",
                "buildId": "untrusted-row-id",
            }
            return httpx.Response(
                200, json={"code": 200, "data": {"list": [] if self.empty_history else [row, row]}}
            )
        response = self.school.handler(request)
        if request.url.path.endswith("selectRoomListByUserId") and response.status_code == 200:
            self.bound_reads += 1
            value = response.json()
            if value["data"]:
                value["data"][0]["balance"] = self.first_balance
            if value["data"] and not self.missing_second:
                second = {
                    **value["data"][0],
                    "roomId": value["data"][0]["roomId"] + "-second",
                    "roomNo": "002",
                    "balance": "98.76",
                }
                value["data"] = [second, *value["data"]]
            return httpx.Response(200, json=value)
        return response


async def cooldown(engine, owner):
    async with engine.begin() as conn:
        await execute(
            conn,
            "UPDATE room_operations SET updated_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 31 SECOND) "
            "WHERE owner_user_id=:owner AND type='balance_refresh'",
            owner=owner.bytes,
        )


async def verify(apps, school):
    query_school = QuerySchool(school)
    apps["school_adapter"].state.school_protocol.transport.transport = httpx.MockTransport(
        query_school.handler
    )
    engine = apps["room"].state.database
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, "synthetic-query-" + str(new_id())))
        owner = UUID(user["id"])
        response = await client.post(
            "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
        )
        assert response.status_code == 202
        assert await sync_tick(apps["room"])
        for _ in range(5):
            await control_tick(apps["room"])
        bindings = (await client.get("/api/v1/room-bindings")).json()["data"]["items"]
        by_number = {b["number"]: UUID(b["id"]) for b in bindings}
        a, b = by_number["001"], by_number["002"]
        baseline = query_school.bound_reads
        responses = await asyncio.gather(
            *(
                client.post(
                    f"/api/v1/room-bindings/{binding}/balance-refresh",
                    headers={"Idempotency-Key": str(new_id())},
                )
                for binding in (a, b)
            )
        )
        assert all(r.status_code == 202 for r in responses), [
            (r.status_code, r.json().get("error", {}).get("code")) for r in responses
        ]
        assert await query_tick(apps["room"])
        assert query_school.bound_reads == baseline + 1
        for binding, expected in ((a, "25.50"), (b, "98.76")):
            balance = (await client.get(f"/api/v1/room-bindings/{binding}/balance")).json()["data"]
            assert balance["amount"] == expected and not balance["stale"]
            principal = Principal("monitoring", owner, 1, new_id())
            collected = await apps["monitoring"].state.service_client.call(
                "school_adapter",
                "/queries/collect",
                "school:collect",
                principal.request_id,
                {"binding_id": str(binding)},
                principal=principal,
            )
            assert collected["balance"] == expected
        print("同账号不同房间/逆序B02：缓存与监控逐roomId匹配；账号合并一次读取：通过")
        before_null = (await client.get(f"/api/v1/room-bindings/{a}/balance")).json()["data"]
        observed = await observe(apps["school_adapter"].state.database, owner, new_id(),
                                 {"data": []}, None, datetime.now(UTC))
        async with engine.begin() as conn:
            await confirm_binding(
                conn,
                owner.bytes,
                {
                    "room_id": "0000-" + user["student_id"],
                    "building": "合成楼栋",
                    "number": "001",
                    "balance": None,
                },
                observation=observed["observation"],
            )
        after_null = (await client.get(f"/api/v1/room-bindings/{a}/balance")).json()["data"]
        assert after_null["amount"] == before_null["amount"]
        assert after_null["fetched_at"] == before_null["fetched_at"] and after_null["stale"]
        print("绑定同步返回未知余额时保留该房间最后成功值与时间：通过")
        await cooldown(engine, owner)
        query_school.missing_second = True
        root = await accept_refresh(engine, owner, a, str(new_id()))
        merged = await accept_refresh(engine, owner, b, str(new_id()))
        await query_tick(apps["room"])
        states = [
            (await client.get(f"/api/v1/operations/{op}")).json()["data"]["state"]
            for op in (root, merged)
        ]
        assert states == ["succeeded", "failed"]
        balance_b = (await client.get(f"/api/v1/room-bindings/{b}/balance")).json()["data"]
        assert balance_b["amount"] == "98.76" and balance_b["stale"]
        print("目标缺失不使用其他房间余额，失败保留原成功值与时间：通过")
        query_school.missing_second = False
        await cooldown(engine, owner)
        await accept_refresh(engine, owner, a, str(new_id()))
        old = await claim_refresh(engine)
        async with engine.begin() as conn:
            await execute(
                conn,
                "UPDATE room_operations SET lease_until=UTC_TIMESTAMP(6) WHERE id=:id",
                id=old["id"],
            )
        current = await claim_refresh(engine)
        assert current["id"] == old["id"] and current["lease_owner"] != old["lease_owner"]
        assert not await finish_refresh(engine, old, [], None)
        assert await finish_refresh(
            engine, current, [{"room_id": "missing", "balance": None}], "SCHOOL_TIMEOUT"
        )
        print("余额短租约接管、迟到结果拒绝与冷却：通过")
        command = HistoryRequest(start_date=date(2026, 9, 20), end_date=date(2026, 9, 29))
        operation = await accept_history(engine, owner, a, command, str(new_id()), new_id())
        first_claim, second_claim = await asyncio.gather(
            claim_history(engine), claim_history(engine)
        )
        claimed = first_claim or second_claim
        assert bool(first_claim) != bool(second_claim)
        async with engine.begin() as conn:
            await execute(
                conn,
                "UPDATE history_sync_windows SET lease_until=UTC_TIMESTAMP(6) WHERE id=:id",
                id=claimed["id"],
            )
        recovered = await claim_history(engine)
        assert recovered["execution_epoch"] > claimed["execution_epoch"]
        assert not await finish_history(engine, claimed, {}, None)
        assert await finish_history(engine, recovered, None, "SCHOOL_TIMEOUT", True)
        async with engine.begin() as conn:
            await execute(
                conn,
                "UPDATE history_sync_windows SET next_attempt_at=UTC_TIMESTAMP(6) "
                "WHERE sync_id=:id",
                id=claimed["sync_id"],
            )
        while await query_tick(apps["room"]):
            pass
        assert (await client.get(f"/api/v1/operations/{operation}")).json()["data"][
            "state"
        ] == "succeeded"
        url = f"/api/v1/room-bindings/{a}/consumption?start_date=2026-09-20&end_date=2026-09-29"
        history = (await client.get(url)).json()["data"]
        assert history["summary"]["amount"] == "6.00" and history["coverage"] == "partial"
        for expected in ("6.00", "8.00", None):
            query_school.amount = "2.00" if expected == "8.00" else "1.50"
            query_school.empty_history = expected is None
            await accept_history(engine, owner, a, command, str(new_id()), new_id())
            while await query_tick(apps["room"]):
                pass
            value = (await client.get(url)).json()["data"]
            assert value["summary"]["amount"] == expected
            assert value["summary"]["complete"] is False
        print(
            "7天窗口/单账号单飞/租约恢复；重复同步不翻倍、同日重复行保留、修订/空窗口不补零：通过"
        )
        response = await client.get("/api/v1/overview")
        assert response.status_code == 200 and response.json()["data"]["profile"]
        assert (await client.get(f"/api/v1/room-bindings/{new_id()}/balance")).status_code == 404
        assert (await client.get(url.replace("2026-09-29", "2099-09-29"))).status_code == 422
        async with engine.connect() as conn:
            pending = await first(
                conn,
                "SELECT COUNT(*) AS n FROM room_operations WHERE owner_user_id=:owner "
                "AND state IN ('accepted','running')",
                owner=owner.bytes,
            )
            assert pending["n"] == 0
        print("总览独立状态/范围保护/对象归属和合成任务终结：通过")


async def main():
    if os.environ.get("ELECT_TEST_DISPOSABLE") != "1":
        raise RuntimeError("仅能使用显式一次性环境")
    apps, school = await fixture_apps()
    try:
        await verify(apps, school)
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if hasattr(app.state, "redis"):
                await app.state.redis.aclose()
            if app.state.database:
                await app.state.database.dispose()
    print("T4查询实际数据库/合成学校验收通过；未访问真实学校")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        if os.environ.get("ELECT_TEST_DEBUG_FRAMES") == "1":
            import traceback

            for frame in traceback.extract_tb(error.__traceback__):
                print(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}")
        raise SystemExit(f"T4查询验收失败（{type(error).__name__}）") from None
