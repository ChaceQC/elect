"""本人B02/C02/D04定向只读诊断；凭据与订单标识仅在内存，不输出原文。"""

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta

from scripts.auth_file import read_auth
from services.common.dates import today
from services.school_adapter.infrastructure.history import records
from services.school_adapter.infrastructure.ocr import solve_image
from services.school_adapter.infrastructure.payment_protocol import check_pay_url
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.rooms import bound_rooms
from services.school_adapter.infrastructure.transport import Deadline, SchoolTransport


class SingleRequest:
    @asynccontextmanager
    async def global_slot(self, deadline, **kwargs):
        deadline.remaining()
        yield

    async def block(self, seconds):
        pass


async def inspect(auth_file, result):
    protocol = SchoolProtocol(SchoolTransport(SingleRequest()))
    challenge = await protocol.challenge()
    answer = await asyncio.to_thread(solve_image, challenge.image)
    if answer is None:
        raise RuntimeError("需要人工验证码")
    student, password = read_auth(auth_file)
    token, user = await protocol.authenticate(
        student, password, {"uid": challenge.uid, "cookies": challenge.cookies}, answer
    )
    del student, password, challenge, answer
    result["authentication"] = "passed"
    value = await protocol.read("/base/roomUser/selectRoomListByUserId", token, {"userId": user})
    rooms = bound_rooms(value)
    result["bound_room_count"] = len(rooms)
    if len(rooms) != 1:
        raise RuntimeError("只允许本人唯一绑定的定向诊断")
    room = rooms[0]["room_id"]
    end, start = today(), today() - timedelta(days=6)
    value = await protocol.read(
        "/base/record/queryRecordByTime", token,
        {"buildId": room, "startTimeStr": start.strftime("%Y%m%d"),
         "endTimeStr": end.strftime("%Y%m%d")}, read_timeout=20,
    )
    history = records(value, start, end)
    result["c02"] = {
        "count": len(history),
        "readings_present": sum(r["last_reading"] is not None and r["reading"] is not None
                                for r in history),
        "latest_date": max((r["record_date"] for r in history), default=None),
    }
    result["d04"] = {}
    for status in (2, 0):
        value = await protocol.read(
            "/base/order/page", token,
            {"buildId": room, "startTimeStr": start.isoformat(), "endTimeStr": end.isoformat(),
             "current": 1, "size": 10, "pageTotal": 100, "orderType": 0,
             "payMethod": 1, "payStatus": status}, deadline=Deadline(25), read_timeout=20,
        )
        data = value.get("data") or {}
        rows = data.get("records") or []
        result["d04"][str(status)] = {
            "count": len(rows), "pages": data.get("pages"),
            "fields": {key: sorted({type(row[key]).__name__ for row in rows if key in row})
                       for key in sorted({key for row in rows for key in row})},
            "statuses": [{key: row[key] for key in ("payStatus", "orderStatus", "orderType",
                                                   "payMethod", "payStatusName")
                          if key in row and type(row[key]) in {int, str}
                          and len(str(row[key])) < 32} for row in rows],
            "room_matches": {key: sum(str(row.get(key)) == room for row in rows)
                             for key in ("buildId", "roomId")},
            "identifier_lengths": {key: sorted({len(str(row.get(key) or "")) for row in rows})
                                   for key in ("orderId", "tradeOrderNo")},
            "matching_paid_amounts": sum(row.get("orderAmount") == row.get("payAmount")
                                         for row in rows),
        }
        if status == 2 and rows:
            try:
                returned = await protocol.read(
                    "/water/order/getPayOrderReturnUrl", token,
                    {"orderId": rows[0]["orderId"]}, read_timeout=20,
                )
                response_data = returned.get("data")
                result["d02_using_sdgl_id"] = {"data_type": type(response_data).__name__}
                if isinstance(response_data, str):
                    prepay = check_pay_url(response_data, accept=True)
                    result["d02_using_sdgl_id"].update(
                        pay_url_valid=True, prepay_length=len(prepay),
                        prepay_equals_sdgl_id=prepay == rows[0]["orderId"],
                    )
            except Exception as error:
                result["d02_using_sdgl_id"] = {
                    "error_code": str(getattr(error, "code", type(error).__name__))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-file", required=True)
    args = parser.parse_args()
    result = {"date": today().isoformat(), "external_business_writes": False}
    try:
        asyncio.run(inspect(args.auth_file, result))
        result["result"] = "passed"
    except Exception as error:
        result.update(result="failed", error_code=str(getattr(error, "code", type(error).__name__)))
    print(json.dumps(result, ensure_ascii=False))
    if result["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
