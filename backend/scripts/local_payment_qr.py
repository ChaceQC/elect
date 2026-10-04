"""用户明确要求的原订单取码恢复；独立持久标记，不重复建学校订单。"""

import argparse
import asyncio
import base64
import io
import json
from pathlib import Path
from urllib.parse import urljoin
from uuid import UUID

import requests
from PIL import Image, ImageOps

from scripts.t2_smoke import fixture_apps
from services.common.sql import first
from services.school_adapter.infrastructure.payment_ledger import PaymentLedger
from services.school_adapter.infrastructure.payment_protocol import (
    check_pay_url,
    form_fields,
    hidden_fields,
    image_bytes,
    qr_url,
)


def fetch(session, method, url, **kwargs):
    check_pay_url(url)
    for _ in range(5):
        response = session.request(method, url, timeout=(5, 45), allow_redirects=False, **kwargs)
        if response.is_redirect:
            if method == "POST" and response.status_code in (307, 308):
                raise RuntimeError("POST_REDIRECT_NOT_REPLAYED")
            url = urljoin(url, response.headers.get("location", ""))
            check_pay_url(url)
            method, kwargs = "GET", {}
            continue
        response.raise_for_status()
        if len(response.content) > 2 * 1024 * 1024:
            raise RuntimeError("RESPONSE_TOO_LARGE")
        response.encoding = "utf-8"
        return response
    raise RuntimeError("TOO_MANY_REDIRECTS")


def save_display(raw, output):
    import cv2
    import numpy as np

    with Image.open(io.BytesIO(raw)) as image:
        padded = ImageOps.expand(image.convert("RGB"), border=16, fill="white")
        display = padded.resize((padded.width * 4, padded.height * 4), Image.Resampling.NEAREST)
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(np.asarray(display))
    if not decoded.startswith("weixin://wxpay/"):
        raise RuntimeError("IMAGE_NOT_VERIFIED_WECHAT_PAYMENT")
    display.save(output, format="PNG")
    output.chmod(0o600)


def recover(payload, crypto, order, output, journal, record):
    aad = f"explicit-qr-recovery:{order}:2026-10-04.1"
    def save(value):
        journal.write_bytes(crypto.seal(value, aad))
        journal.chmod(0o600)

    state = crypto.open(journal.read_bytes(), aad) if journal.exists() else {"step": "E01"}
    record["recovery_step"] = state["step"]
    if state["step"] in {"E02_started", "E03_started"}:
        raise RuntimeError("RECOVERY_UNKNOWN_NOT_REPLAYED")
    if state["step"] == "done":
        save_display(base64.b64decode(state["image"]), output)
        record.update(qr_received=True, qr_target="wechat_payment")
        return
    with requests.Session() as session:
        session.trust_env = False
        session.headers.update({"User-Agent": "Mozilla/5.0", "Connection": "close"})
        for cookie in state.get("cookies", []):
            session.cookies.set(cookie["name"], cookie["value"],
                                domain=cookie["domain"], path=cookie["path"])
        main = urljoin(payload["pay_url"], "PayMain.aspx?prePayId=" + payload["prepay_id"])
        if state["step"] == "E01":
            page = fetch(session, "GET", payload["pay_url"])
            state = {"step": "E02_ready", "fields": hidden_fields(page.text), "referer": page.url}
        for step in ("E02", "E03"):
            if state["step"] != step + "_ready":
                continue
            form = form_fields(state["fields"], step)
            referer = state["referer"]
            state["step"] = step + "_started"
            save(state)
            record["recovery_step"] = state["step"]
            page = fetch(session, "POST", main, data=form, headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": referer,
            })
            state = {"step": "E03_ready" if step == "E02" else "E04_ready",
                     "referer": page.url,
                     "cookies": [{"name": c.name, "value": c.value, "domain": c.domain,
                                  "path": c.path} for c in session.cookies]}
            if step == "E02":
                state["fields"] = hidden_fields(page.text)
            else:
                state["image_url"] = qr_url(page.text, page.url)
            save(state)
        record["recovery_step"] = state["step"]
        picture = fetch(session, "GET", state["image_url"], headers={"Referer": state["referer"]})
        raw, mime = image_bytes(picture.content)
        save_display(raw, output)
        save({"step": "done", "image": base64.b64encode(raw).decode(), "mime": mime})
        record.update(qr_received=True, qr_mime=mime, recovery_step="done",
                      qr_target="wechat_payment")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=UUID, required=True)
    parser.add_argument("--qr-output", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()
    apps, _ = await fixture_apps()
    record = {"date": "2026-10-04", "order_id": str(args.order_id), "new_d01": False}
    try:
        async with apps["payment"].state.database.connect() as conn:
            payment = await first(conn, "SELECT * FROM payment_orders WHERE id=:id",
                                  id=args.order_id.bytes)
        if not payment or str(payment["amount"]) != "1.00" or payment["cancelled_at"]:
            raise RuntimeError("ONLY_ORIGINAL_ONE_YUAN_ORDER")
        ledger = PaymentLedger(apps["school_adapter"].state)
        order = await ledger.get(UUID(bytes=payment["owner_user_id"]), args.order_id)
        if order["state"] != "confirmed":
            raise RuntimeError("ORDER_NOT_CONFIRMED")
        await asyncio.to_thread(recover, ledger.payload(order), ledger.crypto, args.order_id,
                                args.qr_output, args.journal, record)
    except Exception as error:
        record["error_class"] = type(error).__name__
        record["error_code"] = str(getattr(error, "code", "RECOVERY_NOT_COMPLETED"))
    finally:
        for app in apps.values():
            await app.state.service_client.close()
            if app.state.database:
                await app.state.database.dispose()
        await apps["school_adapter"].state.redis.aclose()
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
