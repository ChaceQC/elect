"""显式本人D04只读核验；凭据/票据/原始明细仅在内存，不执行支付写入。"""

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from scripts.auth_file import read_auth
from services.common.dates import today
from services.common.http import ApiError
from services.common.ids import new_id
from services.payment.records_dto import PaymentRecords, PaymentRecordsQuery
from services.school_adapter.application.payment_history import page, read
from services.school_adapter.infrastructure.ocr import solve_image
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.rooms import bound_rooms
from services.school_adapter.infrastructure.transport import Deadline, SchoolTransport


class SerialLimiter:
    @asynccontextmanager
    async def global_slot(self, deadline, *, pool):
        yield

    async def block(self, seconds):
        # Transport接着返回429，本脚本立即停止，不自动重试。
        pass


async def verify(result):
    protocol = SchoolProtocol(SchoolTransport(SerialLimiter()))
    student, password = read_auth(Path(__file__).resolve().parents[2] / "auth.txt")
    deadline = Deadline(90)
    result["stage"] = "authentication"
    for attempt in range(2):
        challenge = await protocol.challenge(deadline=deadline)
        answer = await asyncio.to_thread(solve_image, challenge.image)
        if answer is None:
            continue
        try:
            token, school_user = await protocol.authenticate(
                student, password, {"uid": challenge.uid, "cookies": challenge.cookies},
                answer, deadline=deadline)
            break
        except ApiError as error:
            if error.code != "SCHOOL_LOGIN_REJECTED" or attempt == 1:
                raise
    else:
        raise RuntimeError("captcha_unrecognized")
    del student, password, challenge
    result["stage"] = "bound_rooms"
    rooms = bound_rooms(await protocol.read(
        "/base/roomUser/selectRoomListByUserId", token, {"userId": school_user}))
    result["bound_room_count"] = len(rooms)
    end, start = today(), today() - timedelta(days=29)
    result.update(start_date=str(start), end_date=str(end), rooms=[])
    principal = SimpleNamespace(user_id=new_id(), request_id=new_id())
    for index, room in enumerate(rooms):
        room_id = room["room_id"]

        async def target(*args, room_id=room_id, **kwargs):
            return {"school_room_id": room_id}

        async def school_read(owner, request_id, path, params, *, budget, read_timeout):
            return await protocol.read(path, token, params,
                                       deadline=Deadline(budget), read_timeout=read_timeout)

        state = SimpleNamespace(service_client=SimpleNamespace(call=target),
                                school_sessions=SimpleNamespace(read=school_read))
        command = PaymentRecordsQuery(binding_id=new_id(), start_date=start, end_date=end)
        result["stage"] = "production_parser_and_aggregation"
        records = PaymentRecords.model_validate(await read(state, principal, command))
        evidence = {"room_index": index + 1, "total": records.total,
                    "read_count": len(records.items), "total_amount": records.total_amount,
                    "complete": records.complete,
                    "methods": sorted({r.method for r in records.items if r.method}),
                    "paid_dates_in_range": all(r.paid_at and start <= r.paid_at.date() <= end
                                               for r in records.items),
                    "missing_paid_time": sum(r.paid_at is None for r in records.items)}
        result["rooms"].append(evidence)
        result["stage"] = "channel_comparison"
        value = await protocol.read("/base/order/page", token, {
            "buildId": room_id, "startTimeStr": str(start), "endTimeStr": str(end),
            "current": 1, "size": 10, "pageTotal": 100,
            "orderType": 0, "payStatus": 2, "payMethod": 1})
        wx_rows, wx_total, _ = page(value, 1, room_id)
        evidence.update(wechat_total=wx_total,
                        wechat_first_page_in_all=all(
                            row["id"] in {r.id for r in records.items} for row in wx_rows))
        if records.items and records.items[0].paid_at:
            result["stage"] = "single_day_boundary"
            day = records.items[0].paid_at.date()
            single = PaymentRecords.model_validate(await read(state, principal,
                PaymentRecordsQuery(binding_id=command.binding_id, start_date=day, end_date=day)))
            evidence.update(single_day=str(day), single_day_count=single.total,
                            single_day_complete=single.complete,
                            single_day_includes_selected=records.items[0].id in {
                                r.id for r in single.items},
                            single_day_paid_dates_match=all(
                                r.paid_at and r.paid_at.date() == day for r in single.items))
    result["stage"] = "complete"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    result = {"date": str(today()), "scope": "本人认证、B02、D04只读",
              "external_business_writes": False, "deployed_endpoint_verified": False}
    try:
        asyncio.run(verify(result))
        result["result"] = "passed"
    except Exception as error:
        result.update(result="failed", error_code=str(getattr(error, "code", type(error).__name__)))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["result"] == "passed" else 1)


if __name__ == "__main__":
    main()
