"""一次省略学校验证码的受控认证；仅输出分类，不输出账号/响应/票据。"""

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from scripts.auth_file import read_auth
from services.common.dates import today
from services.school_adapter.infrastructure.protocol import API, CAS, SERVICE, SchoolProtocol
from services.school_adapter.infrastructure.rsa import encrypt_password
from services.school_adapter.infrastructure.transport import Deadline, SchoolTransport, parse_json


class ProbeLimiter:
    @asynccontextmanager
    async def global_slot(self, deadline, *, pool):
        yield


async def probe(path, with_uid=False):
    student, password = read_auth(path)
    transport, deadline = SchoolTransport(ProbeLimiter()), Deadline(50)
    if with_uid:
        protocol = SchoolProtocol(transport)
        challenge = await protocol.challenge(deadline=deadline)
        try:
            await protocol.authenticate(
                student,
                password,
                {"uid": challenge.uid, "cookies": challenge.cookies},
                "",
                deadline=deadline,
            )
            return {
                "result": "authenticated",
                "school_captcha_required": False,
                "getInfo_confirmed": True,
                "kaptcha_requests": 1,
                "login_submissions": 1,
                "variant": "valid_uid_empty_answer",
            }
        except Exception as error:
            from services.common.http import ApiError

            if isinstance(error, ApiError) and error.code == "SCHOOL_LOGIN_REJECTED":
                return {
                    "result": "rejected",
                    "school_captcha_required": None,
                    "empty_answer_rejected": True,
                    "kaptcha_requests": 1,
                    "login_submissions": 1,
                    "variant": "valid_uid_empty_answer",
                }
            raise
    async with transport.client() as client:
        await transport.request(
            client, "GET", CAS + "/login", deadline, params={"service": SERVICE}
        )
        response = await transport.request(
            client,
            "POST",
            CAS + "/v1/tickets",
            deadline,
            data={
                "username": student,
                "password": encrypt_password(password),
                "service": SERVICE,
                "loginType": "",
                "otpcode": "",
            },
        )
        del student, password
        value = parse_json(response, check_code=False, allow_text_json=True)
        ticket = value.get("ticket")
        if not isinstance(ticket, str) or not ticket:
            # 只输出是否明确指出验证码；原始文本可能含个人信息。
            text = json.dumps(value, ensure_ascii=False).lower()
            captcha_error = any(word in text for word in ("验证码", "captcha", "kaptcha"))
            return {
                "result": "rejected",
                "school_captcha_required": True if captcha_error else None,
                "captcha_error_identified": captcha_error,
                "kaptcha_requests": 0,
                "login_submissions": 1,
            }
        callback = await transport.request(
            client,
            "GET",
            httpx.URL(SERVICE).copy_merge_params({"ticket": ticket}),
            deadline,
        )
        tokens = parse_qs(callback.url.query.decode()).get("token", [])
        if len(tokens) != 1:
            raise RuntimeError("回调未确认")
    async with transport.client() as client:
        response = await transport.request(
            client,
            "GET",
            API + "/getInfo",
            deadline,
            authenticated=True,
            headers={"Authorization": "Bearer " + tokens[0]},
        )
        info = parse_json(response, authenticated=True)
        if not isinstance(info.get("user"), dict) or not info["user"].get("userId"):
            raise RuntimeError("学校用户未确认")
    return {
        "result": "authenticated",
        "school_captcha_required": False,
        "getInfo_confirmed": True,
        "kaptcha_requests": 0,
        "login_submissions": 1,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-file", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--with-uid", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(probe(args.auth_file, args.with_uid))
    except Exception as error:
        result = {
            "result": "unverified",
            "failure_class": type(error).__name__,
            "school_captcha_required": None,
        }
    args.record.write_text(
        json.dumps({"date": str(today()), **result}, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
