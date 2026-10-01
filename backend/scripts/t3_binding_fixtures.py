"""学校绑定合成夹具；仅用于显式隔离验收。"""

import json

import httpx

from scripts.t2_fixtures import SyntheticSchool


class BindingSchool(SyntheticSchool):
    def __init__(self):
        super().__init__()
        self.bindings, self.binding_posts = {}, 0
        self.hidden, self.lose_next, self.reject_next = set(), False, False
        self.rooms = {
            f"synthetic-room-{n}": {
                "roomId": f"synthetic-room-{n}",
                "buildingName": "合成枫苑楼",
                "roomNo": str(n),
                "balance": "25.50",
                "userId": "must-be-overridden",
                "userName": "不得公开的候选住户资料",
            }
            for n in [402, 403, 404, 405, 406]
        }

    def handler(self, request):
        path = request.url.path
        if not path.startswith("/api/base/"):
            return super().handler(request)
        user = self.tokens[request.headers["authorization"].removeprefix("Bearer ")]
        assert "cookie" not in request.headers
        if path == "/api/base/baseBuildings/getBuildList":
            assert request.url.params["searchValue"] == ""
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "total": 2,
                        "records": [
                            {"label": "合成枫苑楼", "value": "synthetic-building"},
                            {"label": "合成其他楼", "value": "other"},
                        ],
                    },
                },
            )
        if path == "/api/base/rooms/getAllFoolNumByBuildId":
            assert request.url.params["buildingId"] == "synthetic-building"
            return httpx.Response(
                200, json={"code": 200, "data": [{"label": "4层", "value": "4-synthetic"}]}
            )
        if path == "/api/base/rooms/getRoomListByBuildIdAndFloor":
            assert request.url.params["floorNum"] == "4"
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {"label": value["roomNo"], "value": key}
                        for key, value in self.rooms.items()
                    ],
                },
            )
        if path == "/api/base/rooms/queryRoomList":
            target = request.url.params.get("roomId")
            records = [self.rooms[target]] if target in self.rooms else list(self.rooms.values())
            return httpx.Response(
                200, json={"code": 200, "data": {"records": records, "total": len(records)}}
            )
        if path == "/api/base/roomUser/selectRoomListByUserId":
            assert request.url.params["userId"] == f"school-{user}"
            records = [
                record
                for record in self.bindings.get(user, [])
                if record["roomId"] not in self.hidden
            ]
            return httpx.Response(200, json={"code": 200, "data": records})
        assert path == "/api/base/roomUser/batchAdd" and request.method == "POST"
        records = json.loads(request.content)["roomUsers"]
        assert len(records) == 1 and records[0]["userId"] == f"school-{user}"
        assert records[0]["roomId"] in self.rooms
        self.binding_posts += 1
        if self.reject_next:
            self.reject_next = False
            return httpx.Response(200, json={"code": 500, "msg": "必须脱敏的学校错误"})
        target = records[0]["roomId"]
        self.bindings.setdefault(user, []).append(
            {**records[0], "bruId": f"synthetic-relation-{target}"}
        )
        if self.lose_next:
            self.lose_next = False
            raise httpx.ReadTimeout("synthetic response lost")
        return httpx.Response(200, json={"code": 200})
