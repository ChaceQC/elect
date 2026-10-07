import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.payment.records_dto import PaymentRecords, PaymentRecordsQuery
from services.school_adapter.application.payment_history import page, read


def response(current=1, total=11, **changes):
    rows = [{"orderId": str(i), "buildId": "room", "payStatus": "2", "orderType": "0",
             "payAmount": "0.10", "payMethod": "7", "createdTime": "2026-10-01 09:00:00",
             "payTime": "2026-10-01 10:00:00", **changes}
            for i in range((current - 1) * 10, min(current * 10, total))]
    return {"code": 200, "data": {"records": rows, "total": total, "current": current,
                                 "pages": (total + 9) // 10}}


def setup(responses):
    state = SimpleNamespace(service_client=SimpleNamespace(call=AsyncMock(
        return_value={"school_room_id": "room"})), school_sessions=SimpleNamespace(
            read=AsyncMock(side_effect=responses)))
    principal = SimpleNamespace(user_id=new_id(), request_id=new_id())
    command = PaymentRecordsQuery(binding_id=new_id(), start_date="2026-10-01",
                                  end_date="2026-10-02")
    return state, principal, command


def test_all_channels_exact_total_and_owned_target():
    state, principal, command = setup([response(), response(2)])
    result = PaymentRecords.model_validate(asyncio.run(read(state, principal, command)))
    assert result.total_amount == "1.10" and result.complete and len(result.items) == 11
    assert result.items[0].method == "7"
    assert state.service_client.call.await_args.kwargs["principal"] == principal
    for call in state.school_sessions.read.await_args_list:
        params = call.args[3]
        assert "payMethod" not in params
        assert params["buildId"] == "room" and params["startTimeStr"] == "2026-10-01"


@pytest.mark.parametrize("changes", [{"buildId": "other"}, {"payStatus": "0"},
    {"payAmount": "NaN"}, {"payAmount": "0.001"}, {"payAmount": 1}, {"payTime": "bad"}])
def test_untrusted_rows_are_rejected(changes):
    with pytest.raises(ApiError):
        page(response(total=1, **changes), 1, "room")


@pytest.mark.parametrize("second", [response(2, total=12), response(1),
    ApiError(504, ErrorCode.SCHOOL_TIMEOUT, "timeout")])
def test_partial_is_never_presented_as_total(second):
    state, principal, command = setup([response(), second])
    result = asyncio.run(read(state, principal, command))
    assert not result["complete"] and result["total_amount"] is None
    assert result["known_amount"] == "1.00"


def test_empty_and_auth_failure_and_forbidden_binding():
    state, principal, command = setup([response(total=0)])
    result = asyncio.run(read(state, principal, command))
    assert result["complete"] and result["total_amount"] == "0.00"
    state, principal, command = setup([response(), ApiError(
        429, ErrorCode.RATE_LIMITED, "wait", retry_after_seconds=60)])
    with pytest.raises(ApiError) as caught:
        asyncio.run(read(state, principal, command))
    assert caught.value.retry_after_seconds == 60
    state, principal, command = setup([])
    state.service_client.call.side_effect = ApiError(404, ErrorCode.NOT_FOUND, "missing")
    with pytest.raises(ApiError):
        asyncio.run(read(state, principal, command))
    state.school_sessions.read.assert_not_called()
