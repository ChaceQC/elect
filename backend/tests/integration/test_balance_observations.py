"""R2：真实MySQL三入口交错提交，时钟不参与排序。"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from query_resource_support import database, requires_mysql, run, seed_binding

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import BalanceObservation, BindingQuery
from services.common.security import Principal
from services.common.sql import execute, first
from services.room.balance import accept_refresh, claim_refresh, finish_refresh, get_balance
from services.room.query_api import balance_observed
from services.room.repository import RoomRepository
from services.school_adapter.infrastructure.balance_observations import observe

pytestmark = requires_mysql


def test_adapter_real_bound_and_collect_paths_allocate_inside_account_lock(monkeypatch):
    from services.school_adapter import api, query_api
    from services.school_adapter.application import sessions

    async def verify():
        async with database("school_adapter") as adapter, database("room") as room:
            owner, binding = new_id(), new_id()
            await seed_binding(room, owner, binding)
            locked, fail = False, False

            @asynccontextmanager
            async def account_lock(*args, **kwargs):
                nonlocal locked
                assert not locked
                locked = True
                yield
                locked = False

            row = {"id": new_id().bytes, "status": "active", "version": 1}
            repository = SimpleNamespace(engine=adapter, current=AsyncMock(return_value=row),
                                         payload=lambda row: {"student_id": "synthetic"})

            async def read(*args, **kwargs):
                assert locked
                if fail:
                    raise ApiError(502, "SCHOOL_INVALID_RESPONSE", "synthetic")
                return {"data": [{"roomId": "101", "balance": "25.00"}]}

            original = observe

            async def checked_observe(*args):
                assert locked
                return await original(*args)

            monkeypatch.setattr("services.school_adapter.infrastructure.balance_observations.observe",
                                checked_observe)
            monkeypatch.setattr(sessions, "lookup_aliases", lambda *args: {"v": "synthetic"})
            school = sessions.SchoolSessions(
                repository, SimpleNamespace(account_lock=account_lock),
                SimpleNamespace(read=read), SimpleNamespace(current="v"),
            )
            school.token = AsyncMock(return_value=("synthetic", "synthetic", row))
            principal = Principal("monitoring", owner, 1, new_id())
            room_request = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(database=room)))

            async def call(service, path, scope, request_id, payload, **kwargs):
                if path == "/controls/query-target":
                    return {"school_room_id": "101"}
                return await balance_observed(
                    BalanceObservation(**payload), room_request, principal)

            request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
                school_sessions=school, service_client=SimpleNamespace(call=call))))
            monkeypatch.setattr(query_api, "collect_meter", AsyncMock(return_value=None))
            try:
                bound = await api.bindings(request, principal)
                assert bound["observation"]["sequence"] == 1
                assert await query_api.collect(BindingQuery(binding_id=binding), request,
                                               principal) == {"balance": "25.00"}
                assert (await cache(room, binding))["observation_sequence"] == 2
                fail = True
                with pytest.raises(ApiError):
                    await query_api.collect(BindingQuery(binding_id=binding), request, principal)
                result = await cache(room, binding)
                assert result["balance"] == 25 and result["last_error_sequence"] == 3
                assert result["quality"] == "stale"
            finally:
                await school.ocr_executor.close()
    asyncio.run(verify())


def observation(sequence, *, error=None, hour=10):
    return {"sequence": sequence, "observed_at": datetime(2026, 10, 6, hour, tzinfo=UTC),
            "request_id": new_id(), "source": "school_bound_rooms", "error_code": error}


async def cache(engine, binding):
    async with engine.connect() as conn:
        return await first(conn, "SELECT * FROM room_balance_cache WHERE binding_id=:id",
                           id=binding.bytes)


def test_three_real_writers_keep_success_error_order_and_replay():
    async def case(engine):
        owner, binding = new_id(), new_id()
        await seed_binding(engine, owner, binding)
        async with engine.begin() as conn:
            room = await first(conn, "SELECT room_id FROM room_bindings WHERE id=:id",
                               id=binding.bytes)
            await execute(conn, "UPDATE rooms SET school_id='hbue',school_room_id='101' "
                          "WHERE id=:id", id=room["room_id"])
            await execute(conn, "INSERT INTO room_preferences(owner_user_id,default_binding_id,"
                          "version,state) VALUES(:owner,:binding,1,'ready')",
                          owner=owner.bytes, binding=binding.bytes)
        record = {"room_id": "101", "building": "test", "number": "101", "balance": "20.00"}
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=engine)))
        principal = Principal("school_adapter", owner, 1, new_id())

        async def observed(meta, amount):
            return await balance_observed(BalanceObservation(binding_id=binding, amount=amount,
                                                              **meta), request, principal)

        await accept_refresh(engine, owner, binding, str(new_id()))
        refresh = await claim_refresh(engine)
        assert await observed(observation(3), "30.00") == {"recorded": True}
        assert await finish_refresh(engine, refresh, [record], None, observation(2, hour=12))
        assert (await cache(engine, binding))["balance"] == 30
        repository = RoomRepository(engine)
        await repository.accept_sync(owner, str(new_id()))
        sync = await repository.claim()
        assert await repository.complete(sync, [], "SCHOOL_TIMEOUT", new_id(),
                                         observation(1, error="SCHOOL_TIMEOUT", hour=13))
        assert (await cache(engine, binding))["quality"] == "fresh"
        await repository.accept_sync(owner, str(new_id()))
        sync = await repository.claim()
        record["balance"] = "40.00"
        await repository.complete(sync, [record], None, new_id(), observation(4, hour=9))
        success = await cache(engine, binding)
        assert success["balance"] == 40 and success["fetched_at"].hour == 9
        error = observation(5, error="SCHOOL_TIMEOUT")
        await observed(error, None)
        assert await observed(error, None) == {"recorded": True}
        failed = await cache(engine, binding)
        assert failed["balance"] == 40 and failed["quality"] == "stale"
        assert failed["fetched_at"] == success["fetched_at"]
        assert failed["last_success_sequence"] == 4 and failed["last_error_sequence"] == 5
        meta = observation(6)
        await observed(meta, "50.00")
        with pytest.raises(ApiError) as conflict:
            await observed(meta, "99.00")
        assert conflict.value.code == "VERSION_CONFLICT"
        await observed(observation(7), None)
        assert (await cache(engine, binding))["balance"] == 50
        assert (await get_balance(engine, owner, binding)).stale
        await repository.accept_sync(owner, str(new_id()))
        sync = await repository.claim()
        before = dict(await cache(engine, binding))
        await repository.complete(sync, [], "DEPENDENCY_UNAVAILABLE", new_id())
        assert dict(await cache(engine, binding)) == before
    run("room", case)


def test_owner_sequence_persists_and_bad_school_result_is_ordered():
    async def case(engine):
        owner, other = new_id(), new_id()
        stamp = datetime(2026, 10, 6, tzinfo=UTC)
        first_value = await observe(engine, owner, new_id(), {"data": []}, None, stamp)
        values = await asyncio.gather(*[
            observe(engine, owner, new_id(), None, "SCHOOL_TIMEOUT", stamp) for _ in range(5)
        ])
        assert first_value["observation"]["sequence"] == 1
        assert sorted(item["observation"]["sequence"] for item in values) == list(range(2, 7))
        malformed = await observe(engine, owner, new_id(), {"data": {}}, None, stamp)
        assert malformed["observation"]["sequence"] == 7
        assert malformed["observation"]["error_code"] == "SCHOOL_INVALID_RESPONSE"
        assert (await observe(engine, other, new_id(), {"data": []}, None, stamp)
                )["observation"]["sequence"] == 1
    run("school_adapter", case)


def test_legacy_cache_is_not_given_a_fabricated_observation():
    async def verify():
        async with database("room") as engine:
            owner, binding = new_id(), new_id()
            await seed_binding(engine, owner, binding)
            async with engine.begin() as conn:
                await execute(conn, "INSERT INTO room_balance_cache(binding_id,balance,source,"
                              "quality,fetched_at) VALUES(:id,7,'school_bound_rooms','fresh',"
                              "UTC_TIMESTAMP(6))", id=binding.bytes)
            assert (await get_balance(engine, owner, binding)).stale
            row = await cache(engine, binding)
            assert row["observation_sequence"] is None and row["last_success_sequence"] is None
    asyncio.run(verify())
