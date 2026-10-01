"""显式生产链路烟测：真实学校认证、本人读取，不执行绑定/支付/邮件。"""

import argparse
import asyncio
import json
import ssl
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from scripts.auth_file import read_auth
from services.common.ids import new_id
from services.school_adapter.infrastructure.ocr import solve_image


async def verify(args, record):
    student, password = read_auth(args.auth_file)
    context = ssl.create_default_context(cafile=str(args.ca_file)) if args.ca_file else True
    async with httpx.AsyncClient(
        base_url=args.origin,
        verify=context,
        trust_env=False,
        timeout=105,
        headers={"Origin": args.origin},
    ) as client:
        record["last_stage"] = "agreement"
        agreement = await client.get("/api/v1/auth/agreement")
        agreement.raise_for_status()
        policy = agreement.json()["data"]
        answer, challenge = None, None
        for _ in range(2):
            record["last_stage"] = "captcha"
            response = await client.post("/api/v1/auth/captcha", json={})
            if not response.is_success:
                record["failure_code"] = response.json().get("error", {}).get("code", "HTTP_ERROR")
            response.raise_for_status()
            challenge = response.json()["data"]
            answer = await asyncio.to_thread(solve_image, challenge["image_data_url"])
            if answer is not None:
                break
        if answer is None:
            raise RuntimeError("验证码未识别，未提交学校认证")
        # 只做一次真实登录提交，不在失败后自动重提密码。
        record["last_stage"] = "login"
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "student_id": student,
                "password": password,
                "challenge_id": challenge["challenge_id"],
                "captcha_answer": answer,
                "agreement_version": policy["version"],
                "agreement_accepted": True,
                "credential_use_allowed": True,
            },
        )
        del student, password, answer, challenge
        if not response.is_success:
            record["failure_code"] = response.json().get("error", {}).get("code", "HTTP_ERROR")
            response.raise_for_status()
        me = response.json()["data"]["user"]
        client.headers["X-CSRF-Token"] = me["csrf_token"]
        record["authentication"] = "passed"
        record["production_adapter_verified"] = True
        record["credential_activation"] = me["credential_status"]
        restored = await client.get("/api/v1/auth/me")
        restored.raise_for_status()
        assert restored.json()["data"]["id"] == me["id"]
        record["application_session_restore"] = "passed"
        sync = await client.post(
            "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
        )
        sync.raise_for_status()
        operation = sync.json()["data"]["operation_id"]
        for _ in range(60):
            result = await client.get(f"/api/v1/operations/{operation}")
            result.raise_for_status()
            state = result.json()["data"]
            if state["state"] in {"succeeded", "failed", "cancelled", "unknown"}:
                break
            await asyncio.sleep(1)
        if state["state"] != "succeeded":
            record["binding_sync"] = state["state"]
            record["failure_code"] = state["error_code"]
            raise RuntimeError("真实绑定同步未成功")
        listing = await client.get("/api/v1/room-bindings")
        listing.raise_for_status()
        rooms = listing.json()["data"]
        record.update(
            binding_sync="passed",
            bound_room_count=rooms["total"],
            bindings_sync_status=rooms["sync_status"],
            default_initialization="deferred_to_T3",
        )
        # 查询一页，不全量遍历；不回显房间或其他住户信息。
        candidates = await client.get(
            "/api/v1/room-candidates", params={"page": 1, "page_size": 10}
        )
        if candidates.is_success:
            data = candidates.json()["data"]
            record.update(
                candidate_page="passed",
                candidate_count=len(data["items"]),
                search_quality=data["search_quality"],
            )
        else:
            record.update(
                candidate_page="failed", candidate_error=candidates.json()["error"]["code"]
            )
        logout = await client.post("/api/v1/auth/logout")
        logout.raise_for_status()
        expired = await client.get("/api/v1/auth/me")
        assert (
            expired.status_code == 401 and expired.json()["error"]["code"] == "APP_SESSION_EXPIRED"
        )
        record["application_logout"] = "passed"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-file", type=Path, required=True)
    parser.add_argument("--origin", default="https://elect.test.local")
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args()
    record = {
        "date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "source": "正式 Gateway/Identity/School Adapter/Room + 真实学校",
        "scope": ["A01", "A02", "A03", "A04", "B01", "B02", "B03"],
        "external_business_writes": False,
        "production_adapter_verified": False,
    }
    try:
        asyncio.run(verify(args, record))
        record["result"] = "passed" if record.get("candidate_page") == "passed" else "partial"
    except Exception as error:
        record.update(result="failed", failure_class=type(error).__name__)
    content = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    if args.record:
        args.record.write_text(content)
    print(content, end="")
    if record["result"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
