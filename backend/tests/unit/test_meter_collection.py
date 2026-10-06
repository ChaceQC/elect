import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.common.ids import new_id
from services.common.internal_dto import BindingQuery
from services.common.security import Principal
from services.monitoring import results, worker
from services.monitoring.samples import sample_view
from services.school_adapter import query_api
from services.school_adapter.application import meter_readings
from services.school_adapter.infrastructure.history import records
from services.school_adapter.infrastructure.rooms import bound_rooms

DAY = date(2026, 10, 4)


def parsed(**changes):
    raw = {"time": "2026-10-03", "lastReading": "100", "reading": "102.5",
           "energyUsage": "2.5", **changes}
    return records({"data": {"list": [raw]}}, date(2026, 9, 28), DAY)[0]


@pytest.mark.parametrize("changes,quality,delta", [
    ({}, "meter_not_realtime", "2.5000"),
    ({"reading": "99"}, "meter_negative_delta", "-1.0000"),
    ({"energyUsage": "1"}, "meter_inconsistent", "2.5000"),
])
def test_latest_school_record_keeps_date_source_and_quality(changes, quality, delta):
    row = parsed(**changes)
    meter = meter_readings.latest_meter([row, parsed(time="2026-10-02"), row])
    assert meter["record_date"] == "2026-10-03"
    assert meter["source_record_key"] == row["row_hash"]
    assert (meter["quality"], meter["delta"]) == (quality, delta)


def test_missing_or_ambiguous_latest_meter_is_not_backfilled_or_combined():
    assert meter_readings.latest_meter([]) is None
    assert meter_readings.latest_meter([parsed(), parsed(reading="103")]) is None
    assert meter_readings.latest_meter([parsed(), parsed(time="2026-10-04", reading=None)]) is None


def test_collect_meter_cache_is_scoped_and_c02_failure_keeps_balance(monkeypatch):
    monkeypatch.setattr(meter_readings, "today", lambda: DAY)

    async def verify():
        cache, reads = {}, []

        class Store:
            async def get_secret(self, key):
                return cache.get(key)

            async def put_secret(self, key, value, *, ttl):
                assert ttl == 10800
                cache[key] = value

        class Sessions:
            store = Store()
            fail = False

            async def read_bound(self, owner, request_id, **options):
                value = await self.read(owner, request_id, "selectRoomListByUserId", {}, **options)
                return {"items": bound_rooms(value), "observation": {
                    "sequence": 1, "observed_at": datetime.now(UTC).isoformat(),
                    "request_id": str(request_id), "source": "school_bound_rooms",
                    "error_code": None,
                }}

            async def read(self, owner, request_id, path, params, **options):
                if path.endswith("selectRoomListByUserId"):
                    return {"data": [{"roomId": "other", "balance": "99"},
                                     {"roomId": "target", "balance": "21.47"}]}
                reads.append(params)
                if self.fail:
                    raise TimeoutError()
                return {"data": {"list": [{"time": "2026-10-03", "lastReading": "100",
                                          "reading": "102.5", "energyUsage": "2.5"}]}}

        sessions = Sessions()
        client = SimpleNamespace(call=AsyncMock(return_value={"school_room_id": "target"}))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            service_client=client, school_sessions=sessions)))
        principal = Principal("monitoring", new_id(), 1, new_id())
        binding = BindingQuery(binding_id=new_id())
        first = await query_api.collect(binding, request, principal)
        repeated = await query_api.collect(binding, request, principal)
        assert first == repeated and first["balance"] == "21.47"
        assert first["meter"]["reading"] == "102.5000"
        assert reads == [{"buildId": "target", "startTimeStr": "20260928",
                          "endTimeStr": "20261004"}]
        sessions.fail = True
        other_binding = await query_api.collect(
            BindingQuery(binding_id=new_id()), request, principal)
        assert other_binding == {"balance": "21.47"} and len(reads) == 2
        other_owner = await query_api.collect(
            binding, request, Principal("monitoring", new_id(), 1, new_id()))
        assert other_owner == {"balance": "21.47"} and len(reads) == 3

    asyncio.run(verify())


def test_worker_persists_meter_with_balance_and_sample_api_displays_it(monkeypatch):
    async def verify():
        sample, execution = {}, SimpleNamespace(credential_version=1, run_id=new_id())
        monitor = {"id": new_id().bytes, "owner_user_id": new_id().bytes,
                   "last_sample_id": None, "interval_minutes": 60}
        run = {"id": execution.run_id.bytes, "binding_id": new_id().bytes, "version": 1}

        @asynccontextmanager
        async def fenced(*args):
            yield object(), monitor, run

        async def execute(conn, sql, **params):
            if "INSERT INTO monitor_samples" in sql:
                from sqlalchemy import text
                text(sql).bindparams(**params)
                sample.update(params)

        monkeypatch.setattr(results, "fenced_transaction", fenced)
        monkeypatch.setattr(results, "execute", execute)
        for name in ("finish_attempt", "record_audit", "cycle_succeeded", "on_sample"):
            monkeypatch.setattr(results, name, AsyncMock())
        meter = meter_readings.latest_meter([parsed()])
        monkeypatch.setattr(
            worker, "collect", AsyncMock(return_value={"balance": "21.47", "meter": meter}))
        app = SimpleNamespace(state=SimpleNamespace(database=object()))
        assert await worker.execute_run(app, execution)
        row = {"id": sample["id"], "run_id": sample["run"], "balance": Decimal(sample["balance"]),
               "captured_at": datetime.now(UTC), "previous_captured_at": None,
               "balance_delta": None,
               "meter_last_reading": Decimal(sample["meter_last"]),
               "meter_reading": Decimal(sample["meter_reading"]),
               "meter_delta": Decimal(sample["meter_delta"]),
               "meter_record_date": sample["meter_date"],
               "meter_source_record_key": sample["meter_key"], "meter_is_repeated": True,
               "quality": sample["quality"]}
        view = sample_view(row)
        assert (view.meter_last_reading, view.meter_reading, view.meter_delta) == (
            "100.0000", "102.5000", "2.5000")
        assert view.meter_record_date == date(2026, 10, 3) and view.meter_is_repeated
        assert view.quality == "meter_not_realtime"

    asyncio.run(verify())
