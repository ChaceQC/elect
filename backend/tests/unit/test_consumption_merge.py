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
    assert value["coverage"] == value["sync_status"] == "partial"
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


@pytest.mark.parametrize("count", [1, 7, 30])
@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_all_dates_known_are_complete_even_with_estimates(count, granularity):
    source = history(["0.00"] + [None] * (count - 1))
    source["sync_status"] = "empty"
    value = merge_consumption(source, estimates(["0.00"] + ["1.20"] * (count - 1)), granularity)
    assert value["summary"]["known_days"] == value["summary"]["expected_days"] == count
    assert value["summary"]["complete"] is True
    assert value["coverage"] == "complete" and value["sync_status"] == "ready"
    assert all(bucket["complete"] for bucket in value["buckets"])
    assert value["summary"]["estimated_days"] == count - 1
    if count > 1:
        assert value["summary"]["estimated_amount"] is not None


@pytest.mark.parametrize("state", ["loading", "stale", "failed", "unavailable"])
def test_full_coverage_does_not_hide_school_sync_state(state):
    source = history([None])
    source["sync_status"] = state
    value = merge_consumption(source, estimates(["0.00"]), "day")
    assert value["coverage"] == "complete" and value["summary"]["complete"] is True
    assert value["summary"]["estimated_amount"] == "0.00"
    assert value["sync_status"] == state


def test_school_only_full_coverage_survives_monitor_unavailable():
    client = SimpleNamespace(call=AsyncMock(side_effect=TimeoutError()))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(service_client=client)))
    value = asyncio.run(with_monitoring(request, Principal("gateway", new_id(), 1, new_id()),
                                       history(["0.00", "1.20"]), "week"))
    assert value["coverage"] == "complete" and value["sync_status"] == "ready"
    assert value["monitoring_status"] == "unavailable"
    assert value["summary"]["estimated_amount"] is None


@pytest.mark.parametrize(("school", "estimate", "expected", "estimated"), [
    ("3.90", "4.41", "3.90", None),
    ("0.00", "4.41", "4.41", "4.41"),
    (None, "4.41", "4.41", "4.41"),
    (None, "0.00", "0.00", "0.00"),
    ("0.00", None, "0.00", None),
    ("-0.30", "4.41", "-0.30", None),
    (None, None, None, None),
])
def test_overview_yesterday_uses_same_merged_day_even_when_range_is_partial(
    monkeypatch, school, estimate, expected, estimated,
):
    from services.gateway import query_api

    original = history(["1.00", None, "8.00", school, "2.00"])
    principal = Principal("gateway", new_id(), 1, new_id())

    async def call(domain, path, *args, **kwargs):
        if domain == "monitoring" and path == "/browser/consumption":
            return estimates([None, None, None, estimate, None])
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "合成资料不可用")

    request = SimpleNamespace(cookies={}, app=SimpleNamespace(state=SimpleNamespace(
        service_client=SimpleNamespace(call=AsyncMock(side_effect=call)),
        public_origin="https://synthetic.example",
    )))
    monkeypatch.setattr(query_api, "session", AsyncMock(return_value=(principal, None)))
    monkeypatch.setattr(query_api, "room_call", AsyncMock(return_value={
        "viewing_binding_id": original["binding_id"], "default_binding": None,
        "balance": None, "history": original,
    }))
    monkeypatch.setattr(query_api, "success", lambda request, value: value)

    value = asyncio.run(query_api.overview(request))
    yesterday = next(item for item in value["daily_consumption"]["buckets"]
                     if item["start_date"] == "2026-10-01")
    assert value["summary"]["yesterday_amount"] == yesterday["amount"] == expected
    assert value["summary"]["yesterday_estimated_amount"] == estimated
    assert value["summary"]["complete"] is False
    assert (
        value["summary"]["last_14_days_amount"] == value["daily_consumption"]["summary"]["amount"]
    )


def test_overview_summary_missing_yesterday_does_not_reuse_another_day():
    from services.gateway.consumption import overview_summary

    value = merge_consumption(history(["8.00", "4.41", "2.00"]), estimates([]), "day")
    value["buckets"] = [value["buckets"][2], value["buckets"][0]]
    assert overview_summary(value)["yesterday_amount"] is None
    assert overview_summary(value)["yesterday_estimated_amount"] is None
