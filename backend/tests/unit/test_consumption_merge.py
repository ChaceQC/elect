import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.common.security import Principal
from services.gateway.consumption import merge_consumption, with_monitoring
from services.room.consumption import aggregate
from services.room.dto import Consumption


def history(amounts):
    start = date(2026, 9, 28)
    end = start + timedelta(days=len(amounts) - 1)
    rows = [{"record_date": start + timedelta(days=i), "charged_amount": amount,
             "energy_usage": None} for i, amount in enumerate(amounts)]
    buckets, summary = aggregate(rows, start, end, "day")
    return Consumption(binding_id=new_id(), start_date=start, end_date=end,
                       granularity="day", buckets=buckets, summary=summary, coverage="partial",
                       sync_status="partial", sync_operation=None,
                       version=2).model_dump(mode="json")


def estimates(amounts):
    return {"days": [{"record_date": (date(2026, 9, 28) + timedelta(days=i)).isoformat(),
                      "amount": amount} for i, amount in enumerate(amounts)], "sample_count": 9}


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_merge_daily_before_regroup_school_zero_negative_and_decimal(granularity):
    value = merge_consumption(history(["1.50", "0.00", None, "-0.30", "0.00", None]),
                              estimates(["9.00", "0.10", "0.20", "8.00", "0.00", None]),
                              granularity)
    assert value["summary"] == {"amount": "1.50", "energy_usage": None, "known_days": 5,
                                "expected_days": 6, "complete": False,
                                "estimated_amount": "0.30", "estimated_days": 2}
    assert value["version"] == 11 and value["monitoring_status"] == "ready"
    if granularity == "day":
        assert [b["amount"] for b in value["buckets"]] == [
            "1.50", "0.10", "0.20", "-0.30", "0.00", None]
    elif granularity == "month":
        assert [b["amount"] for b in value["buckets"]] == ["1.80", "-0.30"]
        assert [b["estimated_amount"] for b in value["buckets"]] == ["0.30", None]
    else:
        assert value["buckets"][0]["estimated_days"] == 2


def test_monitor_only_zero_unknown_and_later_school_record_replaces_estimate():
    source = history([None, None])
    source["sync_status"] = "failed"
    value = merge_consumption(source, estimates(["0.00", None]), "day")
    assert value["summary"]["estimated_amount"] == "0.00"
    assert value["summary"]["known_days"] == value["summary"]["estimated_days"] == 1
    assert value["sync_status"] == "failed" and value["coverage"] == "partial"
    refreshed = merge_consumption(history(["2.50", None]), estimates(["1.00", None]), "day")
    assert refreshed["summary"]["amount"] == "2.50"
    assert refreshed["summary"]["estimated_amount"] is None
    assert merge_consumption(history([None]), estimates([None]), "day")["coverage"] == "unknown"


@pytest.mark.parametrize("error", [ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "合成故障"),
                                   ApiError(404, ErrorCode.NOT_FOUND, "旧版本"), TimeoutError()])
def test_monitor_unavailable_preserves_school_data_and_requested_granularity(error):
    client = SimpleNamespace(call=AsyncMock(side_effect=error))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(service_client=client)))
    principal = Principal("gateway", new_id(), 1, new_id())
    original = history(["1.25", "0.00", None])
    value = asyncio.run(with_monitoring(request, principal, original, "month"))
    assert value["monitoring_status"] == "unavailable" and value["granularity"] == "month"
    assert value["summary"]["amount"] == "1.25" and value["summary"]["estimated_amount"] is None
    assert value["version"] == original["version"]
    assert client.call.call_args.kwargs == {"principal": principal, "budget": 5}


def test_gateway_checks_binding_before_monitor_and_requests_daily_data(monkeypatch):
    from services.gateway import query_api

    principal = Principal("gateway", new_id(), 1, new_id())
    original = history(["0.00", None])
    client = SimpleNamespace(call=AsyncMock(return_value=estimates(["1.00", "2.00"])))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(service_client=client)))
    monkeypatch.setattr(query_api, "session", AsyncMock(return_value=(principal, None)))
    room = AsyncMock(return_value=original)
    monkeypatch.setattr(query_api, "room_call", room)
    monkeypatch.setattr(query_api, "success", lambda request, value: value)
    value = asyncio.run(query_api.consumption(new_id(), request, date(2026, 9, 28),
                                            date(2026, 9, 29), "week"))
    assert room.call_args.args[-1]["granularity"] == "day"
    assert value["summary"]["amount"] == "3.00" and value["granularity"] == "week"
    client.call.reset_mock()
    room.side_effect = ApiError(404, ErrorCode.NOT_FOUND, "不属于本人")
    with pytest.raises(ApiError):
        asyncio.run(query_api.consumption(new_id(), request, date(2026, 9, 28),
                                         date(2026, 9, 29), "day"))
    client.call.assert_not_called()
