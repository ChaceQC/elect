import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.ids import new_id
from services.school_adapter.application import payment_orders, payment_records
from services.school_adapter.application.payment_records import (
    confirms_paid,
    order_page,
    same_order,
)

PAYLOAD = {"school_room_id": "room-a", "amount": "1.00", "prepay_id": "original-ticket",
           "sdgl_order_id": None}
PAID = {"orderId": "school-order", "tradeOrderNo": "original-ticket", "buildId": "room-a",
        "orderAmount": "1.00", "payAmount": "1.00", "payStatus": "2", "orderType": "0",
        "payMethod": "1"}


def test_exact_ticket_or_known_school_id_required():
    assert same_order(PAID, PAYLOAD) and confirms_paid(PAID, PAYLOAD)
    assert same_order({**PAID, "orderId": "original-ticket", "tradeOrderNo": ""}, PAYLOAD)
    assert same_order(PAID, {**PAYLOAD, "prepay_id": None, "sdgl_order_id": "school-order"})
    assert not same_order({**PAID, "tradeOrderNo": "other-ticket"}, PAYLOAD)
    assert not same_order(PAID, {**PAYLOAD, "prepay_id": None})


@pytest.mark.parametrize("change", [
    {"buildId": "other-room"}, {"orderAmount": "10.00"}, {"payAmount": "0.00"},
    {"payStatus": 2}, {"payStatus": "PAID"}, {"payStatus": "0"}, {"payAmount": "NaN"},
    {"orderType": "1"}, {"payMethod": "0"},
])
def test_other_rooms_amounts_and_unverified_states_do_not_confirm(change):
    assert not confirms_paid({**PAID, **change}, PAYLOAD)


def test_invalid_business_result_or_page_is_not_a_paid_order():
    for value in ({"code": 500, "data": {}}, {"code": 200, "data": []},
                  {"code": 200, "data": {"records": [PAID], "pages": 0, "current": 1}}):
        with pytest.raises(ApiError):
            order_page(value, 1)


@pytest.mark.parametrize("mode,expected", [
    ("second_page", "paid_confirmed"), ("duplicate", "status_unknown"),
    ("other_ticket", "status_unknown"), ("empty", "status_unknown"),
    ("invalid", "status_unknown"), ("too_many_pages", "status_unknown"),
    ("no_ticket", "submit_unknown"),
])
def test_d04_pagination_preserves_safe_result_without_water_order_api(monkeypatch, mode, expected):
    async def verify():
        calls, observations = [], []
        payload = {**PAYLOAD, "prepay_id": None} if mode == "no_ticket" else PAYLOAD
        row = {"state": "succeeded", "error_code": None, "upstream_operation_id": new_id().bytes,
               "created_at": datetime(2026, 10, 2, 15, 0, tzinfo=UTC)}

        class Sessions:
            async def read(self, owner, request, path, params, **kwargs):
                calls.append(path)
                assert kwargs["budget"] <= 25
                if path.endswith("getPayOrderReturnUrl"):
                    raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "synthetic D02 500")
                assert params["buildId"] == "room-a" and params["payStatus"] == 2
                current = params["current"]
                if mode == "invalid":
                    return {"code": 500}
                if mode == "empty":
                    rows, pages = [], 0
                elif mode == "second_page":
                    rows = [{**PAID, "tradeOrderNo": "other"}] if current == 1 else [PAID]
                    pages = 2
                else:
                    rows, pages = [PAID], 1
                    if mode == "duplicate":
                        rows = [PAID, PAID]
                    elif mode == "other_ticket":
                        rows = [{**PAID, "tradeOrderNo": "other"}]
                    elif mode == "too_many_pages":
                        pages = 6
                return {"code": 200, "data": {"records": rows, "pages": pages, "current": current}}

        @asynccontextmanager
        async def begin():
            yield object()

        def seal(value, aad):
            observations.append(value)
            return b"synthetic-ciphertext"

        school = object.__new__(payment_orders.SchoolOrders)
        school.state = SimpleNamespace(school_sessions=Sessions())
        school.ledger = SimpleNamespace(get=AsyncMock(return_value=row), payload=lambda r: payload,
                                        engine=SimpleNamespace(begin=begin),
                                        crypto=SimpleNamespace(seal=seal))
        monkeypatch.setattr(payment_orders, "execute", AsyncMock())
        result = await school.check(new_id(), new_id(), new_id())
        assert result["order_state"] == expected and observations
        assert all(path == "/base/order/page" for path in calls)
        if expected == "paid_confirmed":
            assert calls == ["/base/order/page", "/base/order/page"]
            assert result["error_code"] is None
        elif mode == "invalid":
            assert observations[0]["D04-error"]["code"] == "SCHOOL_INVALID_RESPONSE"
            assert result["error_code"] == ErrorCode.SCHOOL_INVALID_RESPONSE

    asyncio.run(verify())


@pytest.mark.parametrize("paid_message,user,count,expected", [
    (True, "school-user", 1, True), (False, "school-user", 1, False),
    (True, "other-user", 1, False), (True, "school-user", 2, False),
])
def test_different_school_id_needs_owned_unique_record_and_original_paid_page(
    monkeypatch, paid_message, user, count, expected
):
    async def verify():
        @asynccontextmanager
        async def client():
            yield object()

        message = ("该订单已支付，无法再次交易,请返回系统重新发起交易"
                   if paid_message else "等待付款")
        transport = SimpleNamespace(client=client, request=AsyncMock(
            return_value=SimpleNamespace(text=message)))
        monkeypatch.setattr(payment_records, "PaymentTransport", lambda store: transport)
        state = SimpleNamespace(school_store=object(), school_credentials=SimpleNamespace(
            current=AsyncMock(return_value={}),
            payload=lambda row: {"school_user_id": "school-user"}))
        candidates = [{**PAID, "userId": user}] * count
        payload = {**PAYLOAD, "pay_url": "http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=ticket"}
        observations = {}
        assert await payment_records.confirm_original(
            state, new_id(), payload, candidates, observations, object()) is expected
        if user == "school-user" and count == 1:
            assert transport.request.call_args.args[1:3] == ("GET", payload["pay_url"])
            assert observations["original_payment_page"]["paid_confirmed"] is paid_message
        else:
            transport.request.assert_not_called()

    asyncio.run(verify())
