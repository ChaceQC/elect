"""T2 专用合成学校，永不连接真实学校或发送业务写请求。"""

import base64
import secrets
from urllib.parse import parse_qs

import httpx

from services.school_adapter.infrastructure.rsa import encrypt_password

IMAGE = (
    "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nsynthetic-test-image").decode()
)


class SyntheticSchool:
    def __init__(self):
        self.tokens, self.tickets = {}, {}
        self.posts, self.reads = 0, 0
        self.fail_rooms, self.empty_rooms = False, False
        self.room_numbers = None
        self.reject_login = False

    def handler(self, request):
        path = request.url.path
        if path == "/authserver/login":
            return httpx.Response(
                200, text="CAS", headers={"set-cookie": f"CAS={secrets.token_hex(8)}; Path=/"}
            )
        if path == "/authserver/kaptcha":
            return httpx.Response(
                200, json={"uid": request.headers["cookie"].split("=", 1)[1], "content": IMAGE}
            )
        if path == "/authserver/v1/tickets":
            self.posts += 1
            form = parse_qs(request.content.decode(), keep_blank_values=True)
            assert form["id"][0] in request.headers["cookie"]
            if self.reject_login or form["password"][0] != encrypt_password(" synthetic password "):
                return httpx.Response(200, json={"data": {"code": "rejected"}})
            ticket = secrets.token_hex(16)
            self.tickets[ticket] = form["username"][0]
            return httpx.Response(200, json={"ticket": ticket})
        if path == "/api/sso/callback":
            token = secrets.token_hex(32)
            self.tokens[token] = self.tickets[request.url.params["ticket"]]
            return httpx.Response(302, headers={"location": f"/?token={token}"})
        if path == "/":
            return httpx.Response(200, text="app")
        assert request.method == "GET" and "cookie" not in request.headers
        user = self.tokens[request.headers["authorization"].removeprefix("Bearer ")]
        if path == "/api/getInfo":
            return httpx.Response(200, json={"code": 200, "user": {"userId": f"school-{user}"}})
        self.reads += 1
        if self.fail_rooms:
            return httpx.Response(503)
        record = {
            "roomId": f"0000-{user}",
            "buildingName": "合成楼栋",
            "roomNo": "001",
            "balance": "25.50",
            "userName": "不得泄露的住户资料",
        }
        if path == "/api/base/roomUser/selectRoomListByUserId":
            assert request.url.params["userId"] == f"school-{user}"
            records = [record] if self.room_numbers is None else [
                {**record, "roomId": f"synced-{user}-{number}", "roomNo": number}
                for number in self.room_numbers
            ]
            return httpx.Response(
                200, json={"code": 200, "data": [] if self.empty_rooms else records}
            )
        assert path == "/api/base/rooms/queryRoomList"
        return httpx.Response(200, json={"code": 200, "data": {"records": [record], "total": 1}})
