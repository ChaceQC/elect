"""学校页面 POST 方法覆盖的合成解绑；不访问真实学校。"""

from urllib.parse import unquote

import httpx

from scripts.t3_binding_fixtures import BindingSchool


class RemovalSchool(BindingSchool):
    def __init__(self):
        super().__init__()
        self.remove_posts = 0
        self.lose_remove_next, self.reject_remove_next, self.hold_remove = False, False, False
        self.empty_once = False

    def handler(self, request):
        path = request.url.path
        if path == "/api/base/roomUser/selectRoomListByUserId" and self.empty_once:
            self.empty_once = False
            return httpx.Response(200, json={"code": 200, "data": []})
        if path.startswith("/api/base/roomUser/") and path not in {
            "/api/base/roomUser/selectRoomListByUserId",
            "/api/base/roomUser/batchAdd",
        }:
            assert (
                request.method == "POST" and request.headers["X-HTTP-Method-Override"] == "DELETE"
            )
            assert not request.content
            user = self.tokens[request.headers["authorization"].removeprefix("Bearer ")]
            relation = unquote(path.rsplit("/", 1)[1])
            matches = [
                record for record in self.bindings.get(user, []) if record.get("bruId") == relation
            ]
            assert len(matches) == 1
            self.remove_posts += 1
            if self.reject_remove_next:
                self.reject_remove_next = False
                return httpx.Response(200, json={"code": 500, "msg": "必须脱敏的学校拒绝"})
            if not self.hold_remove:
                self.bindings[user] = [
                    record for record in self.bindings[user] if record.get("bruId") != relation
                ]
            if self.lose_remove_next:
                self.lose_remove_next = False
                raise httpx.ReadTimeout("synthetic removal response lost")
            return httpx.Response(200, json={"code": 200})
        return super().handler(request)
