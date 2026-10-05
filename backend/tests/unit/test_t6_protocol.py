import io

import pytest
from PIL import Image

from services.common.http import ApiError
from services.school_adapter.infrastructure.payment_protocol import (
    check_pay_url,
    form_fields,
    hidden_fields,
    image_bytes,
    original_order_paid,
    qr_url,
)


def test_payment_hidden_fields_entities_and_current_viewstate():
    fields = hidden_fields(
        '<input type="hidden" name="__VIEWSTATE" value="new&amp;state">'
        '<input type="hidden" name="__EVENTVALIDATION" value="new-event">'
    )
    assert fields == {"__VIEWSTATE": "new&state", "__EVENTVALIDATION": "new-event"}
    form = form_fields({**fields, "__ASYNCPOST": "true", "btn_wx": "stale"}, "E03")
    assert form["__VIEWSTATE"] == "new&state" and form["cb"] == "on"
    assert form["btn_wx_show"] == "" and "btn_wx" not in form and "__ASYNCPOST" not in form
    with pytest.raises(ApiError):
        hidden_fields("0|error|500||")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/zhifu/payAccept.aspx?prePayId=abc",
        "http://cwcwx.hbue.edu.cn.evil.example/zhifu/payAccept.aspx?prePayId=abc",
        "http://x@cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=abc",
        "http://cwcwx.hbue.edu.cn:8080/zhifu/payAccept.aspx?prePayId=abc",
        "http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=abc&prePayId=def",
        "http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=%2fsecret",
        "http://sdgl.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=abc",
    ],
)
def test_pay_url_rejects_untrusted_targets_and_ambiguous_ids(url):
    with pytest.raises(ApiError):
        check_pay_url(url, accept=True)


def test_qr_data_encoding_is_preserved_and_html_header_is_not_image_evidence():
    base = "http://cwcwx.hbue.edu.cn/zhifu/PayMain.aspx?prePayId=abc"
    assert qr_url('<img src="MakeQRCode.aspx?data=wx%3A%2F%2Fa%26b">', base).endswith(
        "data=wx%3A%2F%2Fa%26b"
    )
    output = io.BytesIO()
    Image.new("RGB", (133, 133)).save(output, format="PNG")
    assert image_bytes(output.getvalue())[1] == "image/png"
    for invalid in (b"<html>failure</html>", b"\x89PNG\r\n\x1a\n"):
        with pytest.raises(ApiError):
            image_bytes(invalid)


@pytest.mark.parametrize("text", [
    "支付成功", "该订单已失效，请重新发起交易", "该订单未支付",
    "<script>该订单已支付，无法再次交易,请返回系统重新发起交易</script>",
    "<!--该订单已支付，无法再次交易,请返回系统重新发起交易-->",
])
def test_generic_status_scripts_and_comments_do_not_confirm_original_order(text):
    assert not original_order_paid(text)


def test_verified_original_payment_page_message():
    assert original_order_paid(
        '<span>该订单已支付，无法再次交易,请返回系统重新发起交易</span>')
