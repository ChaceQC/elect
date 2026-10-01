"""模拟 D01/D02/D04/E01–E04，状态样本不是学校真实验收证据。"""

import io
import json
from urllib.parse import parse_qs

import httpx
from PIL import Image

from scripts.t3_binding_fixtures import BindingSchool


class PaymentSchool(BindingSchool):
    def __init__(self):
        super().__init__()
        self.payment_posts = {"D01": 0, "E02": 0, "E03": 0}
        self.images = 0
        self.lose, self.reject, self.fail_image = None, False, False
        self.orders = {}
        self.status = "UNPAID"
        output = io.BytesIO()
        Image.new("RGB", (133, 133), "white").save(output, format="PNG")
        self.png = output.getvalue()

    def payment_handler(self, request):
        assert "authorization" not in request.headers
        path = request.url.path
        if path == "/zhifu/payAccept.aspx":
            assert request.method == "GET"
            return httpx.Response(
                200,
                text='<input type="hidden" name="__VIEWSTATE" value="first">',
                headers={"Set-Cookie": "PAY=isolated; Path=/zhifu; HttpOnly"},
            )
        assert "PAY=isolated" in request.headers["cookie"]
        if path == "/zhifu/MakeQRCode.aspx":
            self.images += 1
            assert request.url.params["data"] == "wx://synthetic&data"
            return httpx.Response(
                200,
                content=b"not-image" if self.fail_image else self.png,
                headers={"content-type": "text/html"},
            )
        assert path == "/zhifu/PayMain.aspx" and request.method == "POST"
        fields = parse_qs(request.content.decode(), keep_blank_values=True)
        assert (
            fields["cb"] == ["on"]
            and "__ASYNCPOST" not in fields
            and "ScriptManager1" not in fields
        )
        step = "E02" if "btn_wx" in fields else "E03"
        assert fields["__VIEWSTATE"] == ["first" if step == "E02" else "second"]
        self.payment_posts[step] += 1
        if self.lose == step:
            self.lose = None
            raise httpx.ReadTimeout("synthetic payment response lost")
        return httpx.Response(
            200,
            text='<input type="hidden" name="__VIEWSTATE" value="second">'
            if step == "E02"
            else '<img id="PayImg" src="MakeQRCode.aspx?data=wx%3A%2F%2Fsynthetic%26data">',
        )

    def handler(self, request):
        if request.url.host == "cwcwx.hbue.edu.cn":
            return self.payment_handler(request)
        path = request.url.path
        if path == "/api/base/order/phonePay":
            assert request.method == "POST" and "cookie" not in request.headers
            body = json.loads(request.content)
            assert set(body) == {"userId", "buildId", "orderType", "payMethod", "orderAmount"}
            assert type(body["orderAmount"]) is int
            self.payment_posts["D01"] += 1
            if self.reject:
                self.reject = False
                return httpx.Response(200, json={"code": 500})
            prepay = f"synthetic{self.payment_posts['D01']}"
            self.orders[prepay] = body
            if self.lose == "D01":
                self.lose = None
                raise httpx.ReadTimeout("synthetic D01 lost")
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": f"http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId={prepay}",
                },
            )
        if path == "/api/water/order/getPayOrderReturnUrl":
            assert request.url.params["orderId"] in self.orders
            return httpx.Response(200, json={"code": 200, "data": {"payStatus": self.status}})
        if path == "/api/base/order/page":
            return httpx.Response(200, json={"code": 200, "data": {"records": [], "total": 0}})
        return super().handler(request)
