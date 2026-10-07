"""明确授权的真实学校采集到指定 SMTP 收件人；凭据仅在内存解析。"""

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from scripts.auth_file import read_auth
from scripts.email_auth_file import read_email_auth
from scripts.t2_smoke import browser
from scripts.t5_delivery_smoke import reports
from scripts.t5_fixtures import close_apps, make_job, setup
from services.common.dates import today
from services.common.ids import new_id
from services.common.sql import first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.monitoring.execution import claim_run
from services.monitoring.scheduler import accept_run
from services.monitoring.worker import execute_run
from services.notification.smtp import SmtpTransport
from services.notification.worker import worker_tick
from services.room.worker import control_tick, sync_tick
from services.school_adapter.infrastructure.ocr import solve_image
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.transport import SchoolTransport


async def authenticate(client, path, record, credentials=None):
    record["stage"] = "read_school_credentials"
    student, password = credentials or read_auth(path)
    record["stage"] = "school_captcha"
    policy = (await client.get("/api/v1/auth/agreement")).json()["data"]
    answer = None
    for _ in range(2):
        response = await client.post("/api/v1/auth/captcha", json={})
        if response.status_code != 200:
            record["error_code"] = response.json().get("error", {}).get("code")
            raise RuntimeError("学校验证码未获取")
        challenge = response.json()["data"]
        answer = await asyncio.to_thread(solve_image, challenge["image_data_url"])
        if answer is not None:
            break
    if answer is None:
        record["error_code"] = "CAPTCHA_NOT_SOLVED"
        raise RuntimeError("未识别验证码，未提交认证")
    record["stage"] = "school_login_submit"
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
    if response.status_code != 200:
        record["error_code"] = response.json().get("error", {}).get("code")
        raise RuntimeError("学校登录未通过")
    user = response.json()["data"]["user"]
    client.headers["X-CSRF-Token"] = user["csrf_token"]
    record["school_login_with_captcha"] = "passed"
    return UUID(user["id"])


async def verify(args, record):
    # 用户要求不直接查看文件：只在专用测试进程内解析，不输出任何输入内容。
    smtp_config, recipient = read_email_auth(args.email_auth_file)
    if args.smtp_proxy_url:
        smtp_config = smtp_config.model_copy(update={"proxy_url": args.smtp_proxy_url})
    apps = await setup()
    monitoring, notification, adapter = (
        apps["monitoring"],
        apps["notification"],
        apps["school_adapter"],
    )
    protocol = SchoolProtocol(SchoolTransport(adapter.state.school_store))
    adapter.state.school_protocol = protocol
    adapter.state.school_auth.protocol = protocol
    adapter.state.school_sessions.protocol = protocol
    adapter.state.school_sessions.ocr_executor.solver = solve_image
    notification.state.smtp = SmtpTransport(smtp_config)
    try:
        async with browser(apps["gateway"]) as client:
            record["stage"] = "school_login"
            owner = await authenticate(client, args.auth_file, record, args.school_credentials)
            record["stage"] = "binding_sync"
            response = await client.post(
                "/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())}
            )
            if response.status_code != 202 or not await sync_tick(apps["room"]):
                raise RuntimeError("本人绑定同步未完成")
            for _ in range(5):
                await control_tick(apps["room"])
            config = MonitorConfiguration(monitoring.state.database, monitoring.state.email_crypto)
            saved = await config.get(owner)
            if not saved.binding_id:
                raise RuntimeError("无有效默认寝室")
            response = await client.get(f"/api/v1/room-bindings/{saved.binding_id}/balance")
            amount = response.json()["data"]["amount"]
            if amount is None:
                raise RuntimeError("无真实余额")
            threshold = max(Decimal("1.00"), Decimal(amount) + Decimal("5.00"))
            if threshold > Decimal("10000.00"):
                raise RuntimeError("验收阈值超出政策上限")
            # 验收临时提高阈值、总次数 1；仍由真实 B02 新鲜采集触发，不伪造余额。
            await config.patch(
                owner,
                MonitorPatch(
                    expected_version=saved.version,
                    enabled=True,
                    email=recipient,
                    repeat_limit=1,
                    threshold=format(threshold, ".2f"),
                ),
                new_id(),
            )
            try:
                record["stage"] = "real_collection"
                run = await accept_run(monitoring.state.database, owner, str(new_id()), new_id())
                execution = await claim_run(monitoring.state.database, UUID(bytes=run["id"]))
                if not execution or not await execute_run(monitoring, execution):
                    raise RuntimeError("真实采集失败")
                async with monitoring.state.database.connect() as conn:
                    row = await first(
                        conn,
                        "SELECT last_sample_id FROM monitors WHERE owner_user_id=:id",
                        id=owner.bytes,
                    )
                job, _ = await make_job(apps, UUID(bytes=row["last_sample_id"]))
                if not job:
                    raise RuntimeError("未产生合法邮件工作")
                record["real_B02_fresh_sample"] = "passed"
                record["stage"] = "smtp_delivery"
                # 本地验收只执行这一封；unknown 不重发，临时错误交由持久台账记录。
                await worker_tick(notification, UUID(bytes=job["id"]))
                await reports(apps)
                async with notification.state.database.connect() as conn:
                    delivery = await first(
                        conn,
                        "SELECT state,attempt_count,last_error_code FROM notification_jobs "
                        "WHERE id=:id",
                        id=job["id"],
                    )
                summary = await config.get(owner)
                record.update(
                    smtp_result=delivery["state"],
                    smtp_attempt_count=delivery["attempt_count"],
                    smtp_error_code=delivery["last_error_code"],
                    monitoring_result=summary.notification.state,
                    actual_recipient_scope="email_auth.txt指定的唯一测试收件人",
                    inbox_received="awaiting_user_confirmation",
                    automatic_resend=False,
                )
                record["result"] = (
                    "passed"
                    if delivery["state"] == "sent" and summary.notification.state == "sent"
                    else "partial"
                )
            finally:
                latest = await config.get(owner)
                # 恢复此前设置并明确关闭验收监控，避免后续周期再次给指定邮箱外发。
                await config.patch(
                    owner,
                    MonitorPatch(
                        expected_version=latest.version,
                        **{**saved.config.model_dump(), "enabled": False},
                    ),
                    new_id(),
                )
                record["monitor_configuration_restored"] = True
                await client.post("/api/v1/auth/logout")
    finally:
        await close_apps(apps)


def main():
    parser = argparse.ArgumentParser()
    auth_source = parser.add_mutually_exclusive_group(required=True)
    auth_source.add_argument("--auth-file", type=Path)
    auth_source.add_argument("--school-auth-stdin", action="store_true")
    parser.add_argument("--email-auth-file", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    args.school_credentials = None
    args.smtp_proxy_url = None
    record = {
        "date": str(today()),
        "source": "正式业务代码/实际MySQL/内部ASGI/真实学校B02/真实SMTP",
        "scope": "仅一个指定收件人一次投递，学校只读，临时验收阈值高于实际余额",
    }
    try:
        if args.school_auth_stdin:
            value = json.loads(sys.stdin.read(8192))
            if not {"student", "password"} <= set(value) <= {
                "student",
                "password",
                "proxy_url",
            } or not all(isinstance(v, str) and v for v in value.values()):
                raise RuntimeError("本地凭据进程输入无效")
            args.school_credentials = value["student"], value["password"]
            if value.get("proxy_url"):
                from pydantic import SecretStr

                args.smtp_proxy_url = SecretStr(value["proxy_url"])
            del value
        asyncio.run(verify(args, record))
    except Exception as error:
        record.update(result="failed", failure_class=type(error).__name__)
    args.record.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False))
    raise SystemExit(0 if record.get("result") == "passed" else 1)


if __name__ == "__main__":
    main()
