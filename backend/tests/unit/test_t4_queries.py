import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.common.dates import utc_bounds, windows
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import BindingQuery
from services.common.security import Principal
from services.room.consumption import aggregate
from services.school_adapter.infrastructure.history import records
from services.school_adapter.query_api import collect


def test_shanghai_boundaries_and_seven_day_windows():
    start, end = utc_bounds(date(2026, 9, 28), date(2026, 9, 30))
    assert start.isoformat() == "2026-09-27T16:00:00"
    assert end.isoformat() == "2026-09-30T16:00:00"
    assert list(windows(date(2026, 9, 20), date(2026, 9, 28))) == [
        (date(2026, 9, 20), date(2026, 9, 26)),
        (date(2026, 9, 27), date(2026, 9, 28)),
    ]


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_clipped_buckets_decimal_zero_duplicates_and_unknown(granularity):
    rows = [
        {"record_date": date(2026, 9, 27), "charged_amount": "100.00", "energy_usage": None},
        {"record_date": date(2026, 9, 28), "charged_amount": "0.10", "energy_usage": "0.1000"},
        {"record_date": date(2026, 9, 28), "charged_amount": "0.20", "energy_usage": "0.2000"},
        {"record_date": date(2026, 10, 1), "charged_amount": "0.00", "energy_usage": "0.0000"},
    ]
    buckets, total = aggregate(rows, date(2026, 9, 28), date(2026, 10, 1), granularity)
    assert total == {
        "amount": "0.30",
        "energy_usage": "0.3000",
        "known_days": 2,
        "expected_days": 4,
        "complete": False,
    }
    assert sum(Decimal(b["amount"]) for b in buckets if b["amount"] is not None) == Decimal("0.30")
    assert buckets[0]["start_date"] == date(2026, 9, 28)
    assert buckets[-1]["end_date"] == date(2026, 10, 1)
    if granularity == "day":
        assert [b["amount"] for b in buckets] == ["0.30", None, None, "0.00"]


def test_c02_same_day_duplicates_and_request_provenance():
    row = {
        "time": "2026-09-29",
        "buildId": "untrusted-other-room",
        "trueAmount": "1.50",
        "energyUsage": "2.5",
        "lastReading": "100",
        "reading": "102.5",
    }
    parsed = records({"data": {"list": [row, row]}}, date(2026, 9, 28), date(2026, 9, 30))
    assert len(parsed) == 2 and parsed[0] == parsed[1]
    assert parsed[0]["charged_amount"] == "1.50"
    assert "buildId" not in parsed[0] and parsed[0]["quality"] == "unverified_coverage"
    assert records({"data": {"list": []}}, date(2026, 9, 28), date(2026, 9, 30)) == []


@pytest.mark.parametrize(
    "row",
    [
        {"time": "2026-10-01"},
        {"time": "bad"},
        {"time": "2026-09-29", "trueAmount": True},
        {"time": "2026-09-29", "trueAmount": "NaN"},
    ],
)
def test_c02_invalid_window_is_rejected(row):
    with pytest.raises(ApiError):
        records({"data": {"list": [row]}}, date(2026, 9, 28), date(2026, 9, 30))


@pytest.mark.parametrize("reverse", [False, True])
def test_collect_uses_exact_room_for_same_account(reverse):
    asyncio.run(check_collect_rooms(reverse))


async def check_collect_rooms(reverse):
    bindings = {new_id(): "school-a", new_id(): "school-b"}

    class Client:
        async def call(self, receiver, path, scope, request_id, payload, **kwargs):
            return {
                "school_room_id": bindings[
                    next(b for b in bindings if str(b) == payload["binding_id"])
                ]
            }

    class Sessions:
        store = SimpleNamespace(get_secret=AsyncMock(return_value=None), put_secret=AsyncMock())

        async def read(self, *args, **kwargs):
            rows = [
                {"roomId": "school-a", "balance": "12.34"},
                {"roomId": "school-b", "balance": "98.76"},
            ]
            return {"data": rows[::-1] if reverse else rows}

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(service_client=Client(), school_sessions=Sessions())
        )
    )
    principal = Principal("monitoring", new_id(), 1, new_id())
    values = [await collect(BindingQuery(binding_id=b), request, principal) for b in bindings]
    assert values == [{"balance": "12.34"}, {"balance": "98.76"}]


def test_collect_missing_target_does_not_use_another_room():
    asyncio.run(check_missing_room())


async def check_missing_room():
    class Client:
        async def call(self, *args, **kwargs):
            return {"school_room_id": "missing-target"}

    class Sessions:
        async def read(self, *args, **kwargs):
            return {"data": [{"roomId": "other-room", "balance": "98.76"}]}

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(service_client=Client(), school_sessions=Sessions())
        )
    )
    with pytest.raises(ApiError):
        await collect(
            BindingQuery(binding_id=new_id()),
            request,
            Principal("monitoring", new_id(), 1, new_id()),
        )
